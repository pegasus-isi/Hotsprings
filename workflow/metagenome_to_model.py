#!/usr/bin/env python3
"""
SubductCR Metagenome-to-Model Workflow  (Pegasus WMS)
=====================================================
Portable: one generator, any HPC site, all paths from config/workflow_sites.conf.

  python3 workflow/metagenome_to_model.py --site nersc            # full, NERSC
  python3 workflow/metagenome_to_model.py --site usc   --test     # 2-sample, USC
  python3 workflow/metagenome_to_model.py --site usc   --cpu      # CPU-only
  python3 workflow/metagenome_to_model.py --site nersc --plan-only
"""
import os, glob, argparse
from pathlib import Path
from Pegasus.api import (Workflow, Job, File, Container, Transformation,
    TransformationCatalog, ReplicaCatalog, Properties, Namespace)

ROOT = Path(__file__).resolve().parent.parent
BIN  = ROOT / "bin"
DATA = ROOT / "data"
MAGS = DATA / "mags"


# ---- site config (loaded from config/workflow_sites.conf) ------------------
def load_sites():
    cfg = ROOT / "config" / "workflow_sites.conf"
    sites, cur = {}, None
    if cfg.exists():
        for raw in cfg.read_text().splitlines():
            line = raw.rstrip()
            if not line.strip() or line.strip().startswith("#"):
                continue
            if not line.startswith(" "):
                cur = line.rstrip(":").strip(); sites[cur] = {}
            elif cur and ":" in line:
                k, v = line.strip().split(":", 1)
                sites[cur][k.strip()] = v.strip().strip('"').strip("'")
    return sites

SITES = load_sites()


# ---- resolve the full configuration from args + config --------------------
def resolve_config(args):
    """Return a dict with everything the build needs, from the chosen site."""
    profile = args.site or os.environ.get("MAG_SITE_PROFILE", "nersc")
    profile = profile.lower()
    site = SITES.get(profile)
    if site is None:
        raise SystemExit(f"ERROR: site '{profile}' not in config/workflow_sites.conf "
                         f"(have: {', '.join(SITES) or 'none'})")

    reads = Path(os.environ.get("MAG_READS_DIR", site.get("reads_dir", str(DATA/"metagenome")))).resolve()
    ref   = Path(os.environ.get("MAG_REF_DIR",   site.get("reference", str(DATA/"reference")))).resolve()
    kofam = os.environ.get("MAG_KOFAM_DB", site.get("kofam_db", "")) or ""
    func  = os.environ.get("MAG_FUNC_DB",  site.get("func_db",  "")) or ""
    sifd  = os.environ.get("MAG_SIF_DIR",  site.get("sif_dir",  "")) or str(ROOT/"containers"/"sif")
    kofam = os.path.abspath(kofam) if kofam else ""
    func  = os.path.abspath(func)  if func  else ""
    sifd  = os.path.abspath(sifd)

    # samples: env override -> auto-detect from reads -> baked-in default
    samples = os.environ.get("MAG_METAGENOMES", "").split()
    if not samples:
        r1 = sorted(glob.glob(str(reads / "*_R1.fastq.gz")))
        samples = [os.path.basename(x).replace("_R1.fastq.gz", "") for x in r1]
    if not samples:
        samples = ("ARS BQF BQS BR1F BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETS FAS "
                   "MTF PBS PFF PFS PGF PGS PLS QH2F QHS2 QNF QNS RSF RSS RVF "
                   "SIF SIS SLF SLS TCF TCS").split()
    if args.test:
        samples = samples[:2]

    return {
        "profile": profile,
        "site":    site,
        "runtime": site.get("runtime", "shifter"),
        "cpu_queue": site.get("cpu_queue", "regular"),
        "gpu_queue": site.get("gpu_queue", "regular"),
        "gpu_arg":   site.get("gpu_arg", ""),
        "cpu_arg":   site.get("cpu_arg", ""),
        "exec_site": site.get("exec_site", "compute"),
        "reads": reads, "ref": ref, "kofam": kofam, "func": func, "sifd": sifd,
        "samples": samples,
        "use_gpu": (not args.cpu) and os.environ.get("MAG_GPU", "1") == "1",
        "existing_mags": os.environ.get("MAG_EXISTING", "").split(),
    }


# ---- containers ------------------------------------------------------------
def make_containers(cfg):
    user = os.environ.get("MAG_DOCKER_USER", "swarmourr")
    tag  = os.environ.get("MAG_TAG", "latest")
    runtime, sifd = cfg["runtime"], cfg["sifd"]
    def container(name, image):
        if runtime == "shifter":
            return Container(name, Container.SHIFTER, image=f"shifter:///{image}", bypass_staging=True)
        if runtime == "singularity":
            return Container(name, Container.SINGULARITY,
                             image=f"file://{sifd}/{name}.sif", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")
    names = ["qc","assembly","map","semibin","comebin","vamb","refine","dram","mmseqs","coverm","r"]
    return {n: container(f"mag-{n}", f"{user}/mag-{n}:{tag}") for n in names}


# ---- transformations -------------------------------------------------------
def make_transformations(ctr, cfg):
    def T(name, container, mem_gb=32, cpus=16, gpus=0, runtime=86400):
        t = Transformation(name, site="local", pfn=str(BIN/name), is_stageable=True, container=container)
        for k, v in [("memory", mem_gb*1024), ("cores", cpus), ("runtime", runtime), ("maxwalltime", runtime//60)]:
            t.add_profiles(Namespace.PEGASUS, key=k, value=str(v))
        # DB paths to every job
        if cfg["kofam"]: t.add_profiles(Namespace.ENV, key="MAG_KOFAM_DB", value=cfg["kofam"])
        if cfg["func"]:  t.add_profiles(Namespace.ENV, key="MAG_FUNC_DB",  value=cfg["func"])
        want_gpu = bool(gpus) and cfg["use_gpu"]
        t.add_profiles(Namespace.PEGASUS, key="queue", value=cfg["gpu_queue"] if want_gpu else cfg["cpu_queue"])
        if want_gpu:
            t.add_profiles(Namespace.PEGASUS, key="gpus", value=str(gpus))
            if cfg["gpu_arg"]: t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=cfg["gpu_arg"])
            t.add_profiles(Namespace.ENV, key="MAG_GPU", value="1")
        else:
            if cfg["cpu_arg"]: t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=cfg["cpu_arg"])
            t.add_profiles(Namespace.ENV, key="MAG_GPU", value="0")
        return t
    tc = TransformationCatalog()
    tents = {
        "qc_trim":      T("qc_trim",      ctr["qc"],       mem_gb=16,  cpus=16),
        "assembly":     T("assembly",     ctr["assembly"], mem_gb=120, cpus=64),
        "read_map":     T("read_map",     ctr["map"],      mem_gb=32,  cpus=16),
        "bin_semibin":  T("bin_semibin",  ctr["semibin"],  mem_gb=64,  cpus=16, gpus=1),
        "bin_comebin":  T("bin_comebin",  ctr["comebin"],  mem_gb=64,  cpus=16, gpus=1),
        "bin_vamb":     T("bin_vamb",     ctr["vamb"],     mem_gb=64,  cpus=16, gpus=1),
        "refine":       T("refine",       ctr["refine"],   mem_gb=48,  cpus=16),
        "dram":         T("dram",         ctr["dram"],     mem_gb=64,  cpus=16),
        "mmseqs_func":  T("mmseqs_func",  ctr["mmseqs"],   mem_gb=48,  cpus=16, gpus=1),
        "mmseqs_metal": T("mmseqs_metal", ctr["mmseqs"],   mem_gb=16,  cpus=4),
        "abundance":    T("abundance",    ctr["coverm"],   mem_gb=32,  cpus=16),
        "merge":        T("merge",        ctr["r"],        mem_gb=16,  cpus=4),
        "predict":      T("predict",      ctr["r"],        mem_gb=16,  cpus=4),
    }
    tc.add_transformations(*tents.values())
    seen = {}
    for c in ctr.values():
        if c.name not in seen: tc.add_containers(c); seen[c.name] = True
    return tc, tents


# ---- replicas --------------------------------------------------------------
def make_replicas(cfg):
    rc = ReplicaCatalog()
    reads, ref = cfg["reads"], cfg["ref"]
    def add(l, p): rc.add_replica("local", l, str(p))
    for m in cfg["samples"]:
        add(f"{m}_R1.fastq.gz", reads / f"{m}_R1.fastq.gz")
        add(f"{m}_R2.fastq.gz", reads / f"{m}_R2.fastq.gz")
    for mag in cfg["existing_mags"]:
        add(f"{mag}.fasta", MAGS / f"{mag}.fasta")
    add("metal_genes.ref",  ref / "metal_genes.ref")
    add("geochemistry.csv", ref / "geochemistry.csv")
    return rc


# ---- workflow --------------------------------------------------------------
def build_workflow(T, cfg):
    wf = Workflow("subductcr-metagenome-to-model")
    metal_ref = File("metal_genes.ref"); geochem = File("geochemistry.csv")
    mag_files = {m: File(f"{m}.fasta") for m in cfg["existing_mags"]}
    mags_for_annot = list(cfg["existing_mags"]); coverage_files = {}
    for m in cfg["samples"]:
        r1, r2 = File(f"{m}_R1.fastq.gz"), File(f"{m}_R2.fastq.gz")
        t1, t2 = File(f"{m}_trim_R1.fastq.gz"), File(f"{m}_trim_R2.fastq.gz")
        wf.add_jobs(Job(T["qc_trim"], _id=f"qc_{m}").add_args(r1,r2,t1,t2)
                    .add_inputs(r1,r2).add_outputs(t1,t2,stage_out=False,register_replica=False))
        contigs = File(f"{m}_contigs.fasta")
        wf.add_jobs(Job(T["assembly"], _id=f"assembly_{m}").add_args(t1,t2,contigs)
                    .add_inputs(t1,t2).add_outputs(contigs,stage_out=False,register_replica=False))
        bam = File(f"{m}_sorted.bam")
        wf.add_jobs(Job(T["read_map"], _id=f"map_{m}").add_args(contigs,t1,t2,bam)
                    .add_inputs(contigs,t1,t2).add_outputs(bam,stage_out=False,register_replica=False))
        sb, cb, vb = File(f"{m}_bins_semibin.tar"), File(f"{m}_bins_comebin.tar"), File(f"{m}_bins_vamb.tar")
        wf.add_jobs(Job(T["bin_semibin"], _id=f"semibin_{m}").add_args(contigs,bam,sb)
                    .add_inputs(contigs,bam).add_outputs(sb,stage_out=False,register_replica=False))
        wf.add_jobs(Job(T["bin_comebin"], _id=f"comebin_{m}").add_args(contigs,bam,cb)
                    .add_inputs(contigs,bam).add_outputs(cb,stage_out=False,register_replica=False))
        wf.add_jobs(Job(T["bin_vamb"], _id=f"vamb_{m}").add_args(contigs,bam,vb)
                    .add_inputs(contigs,bam).add_outputs(vb,stage_out=False,register_replica=False))
        refined = File(f"{m}_mags.fasta")
        wf.add_jobs(Job(T["refine"], _id=f"refine_{m}").add_args(contigs,sb,cb,vb,refined)
                    .add_inputs(contigs,sb,cb,vb).add_outputs(refined,stage_out=True,register_replica=True))
        cov = File(f"{m}_coverage.tsv")
        wf.add_jobs(Job(T["abundance"], _id=f"abund_{m}").add_args(refined,t1,t2,cov)
                    .add_inputs(refined,t1,t2).add_outputs(cov,stage_out=True,register_replica=True))
        coverage_files[m] = cov
        mag_files[f"{m}_new"] = refined; mags_for_annot.append(f"{m}_new")
    metal_hits = []
    for mag in mags_for_annot:
        mf = mag_files[mag]
        ann = File(f"{mag}_dram.tsv")
        wf.add_jobs(Job(T["dram"], _id=f"dram_{mag}").add_args(mf,ann)
                    .add_inputs(mf).add_outputs(ann,stage_out=True,register_replica=True))
        func = File(f"{mag}_functional.tsv")
        wf.add_jobs(Job(T["mmseqs_func"], _id=f"func_{mag}").add_args(mf,func)
                    .add_inputs(mf).add_outputs(func,stage_out=True,register_replica=True))
        hits = File(f"{mag}_metal_hits.tsv")
        wf.add_jobs(Job(T["mmseqs_metal"], _id=f"metal_{mag}").add_args(ann,metal_ref,hits)
                    .add_inputs(ann,metal_ref).add_outputs(hits,stage_out=True,register_replica=True))
        metal_hits.append(hits)
    integrated = File("integrated_table.tsv")
    merge_inputs = list(coverage_files.values()) + metal_hits
    wf.add_jobs(Job(T["merge"], _id="merge").add_args(geochem,integrated,*merge_inputs)
                .add_inputs(geochem,*merge_inputs).add_outputs(integrated,stage_out=True,register_replica=True))
    results = File("metal_prediction.tsv")
    wf.add_jobs(Job(T["predict"], _id="predict").add_args(integrated,results)
                .add_inputs(integrated).add_outputs(results,stage_out=True,register_replica=True))
    return wf


# ---- properties ------------------------------------------------------------
def make_properties(cfg):
    p = Properties()
    p["dagman.retry"] = "3"
    p["pegasus.integrity.checking"] = "none"
    p["pegasus.transfer.worker.package"] = "true"
    p["pegasus.transfer.worker.package.autodownload"] = "false"
    p["pegasus.transfer.worker.package.strict"] = "false"
    p["dagman.maxjobs"] = os.environ.get("MAG_MAXJOBS", "20")
    p["dagman.maxidle"] = "40"
    return p


# ---- main ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="SubductCR Metagenome-to-Model workflow")
    ap.add_argument("--site", choices=list(SITES) or ["nersc","usc","slurm"], default=None,
                    help="target HPC site profile (from config/workflow_sites.conf)")
    ap.add_argument("--test", action="store_true", help="only the first 2 samples")
    ap.add_argument("--cpu",  action="store_true", help="CPU-only (disable GPU)")
    ap.add_argument("--plan-only", action="store_true", help="plan but do not submit")
    args = ap.parse_args()

    cfg = resolve_config(args)
    ctr = make_containers(cfg)
    tc, T = make_transformations(ctr, cfg)
    rc = make_replicas(cfg)
    props = make_properties(cfg)
    wf = build_workflow(T, cfg)
    wf.add_transformation_catalog(tc); wf.add_replica_catalog(rc); props.write()

    print("SubductCR Metagenome-to-Model workflow")
    print(f"  site       : {cfg['profile']}  (runtime={cfg['runtime']}, cpu_q={cfg['cpu_queue']}, gpu_q={cfg['gpu_queue']})")
    print(f"  GPU        : {'ON' if cfg['use_gpu'] else 'OFF'}")
    print(f"  mode       : {'TEST (first 2 samples)' if args.test else 'FULL'}")
    print(f"  reads      : {cfg['reads']}")
    print(f"  reference  : {cfg['ref']}")
    print(f"  kofam db   : {cfg['kofam'] or '(unset)'}")
    print(f"  func db    : {cfg['func'] or '(unset)'}")
    print(f"  sif dir    : {cfg['sifd'] if cfg['runtime']=='singularity' else '(shifter)'}")
    print(f"  samples    : {len(cfg['samples'])}")
    print(f"  exec site  : {cfg['exec_site']}")

    plan_kwargs = dict(submit=not args.plan_only, dir=str(ROOT/"runs"),
                       sites=[cfg["exec_site"]], output_sites=["local"])
    wf.plan(**plan_kwargs)


if __name__ == "__main__":
    main()
