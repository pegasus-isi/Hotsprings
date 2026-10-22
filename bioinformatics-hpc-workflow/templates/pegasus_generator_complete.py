#!/usr/bin/env python3
"""
COMPLETE reference generator — a portable bioinformatics Pegasus workflow,
proven on real HPC runs. Shows every pattern: SITE profiles, GPU toggle,
per-sample fan-out, convergence, properties with the fixes that matter.
Adapt the TOOLS, SAMPLES, and job wiring to your pipeline.
"""
import os, glob, argparse
from pathlib import Path
from Pegasus.api import (Workflow, Job, File, Container, Transformation,
    TransformationCatalog, ReplicaCatalog, Properties, Namespace)

ROOT = Path(__file__).resolve().parent.parent
BIN, DATA, REF = ROOT/"bin", ROOT/"data", ROOT/"data"/"reference"
READS = Path(os.environ.get("READS_DIR", str(DATA/"reads")))

# ---- SITE PROFILES (portability: one workflow, any HPC) --------------------
PROFILE = os.environ.get("SITE_PROFILE", "nersc").lower()
_SITE = {
  "nersc": {"runtime":"shifter","cpu_queue":"regular","gpu_queue":"regular",
            "gpu_arg":"-C gpu","cpu_arg":"-C cpu","exec_site":"compute"},
  "usc":   {"runtime":"singularity","cpu_queue":"main","gpu_queue":"gpu",
            "gpu_arg":"--gres=gpu:a100:1","cpu_arg":"","exec_site":"usc"},
  "slurm": {"runtime":"singularity","cpu_queue":"compute","gpu_queue":"gpu",
            "gpu_arg":"--gres=gpu:1","cpu_arg":"","exec_site":"condorpool"},
}
SITE = _SITE.get(PROFILE, _SITE["nersc"])
USE_GPU = os.environ.get("USE_GPU", "1") == "1"   # one switch for CPU-only

# ---- containers (runtime from the site profile) ---------------------------
def make_containers():
    user = os.environ.get("DOCKER_USER", "myns"); tag = os.environ.get("TAG", "latest")
    def c(name, image):
        if SITE["runtime"] == "shifter":
            return Container(name, Container.SHIFTER, image=f"shifter:///{image}", bypass_staging=True)
        if SITE["runtime"] == "singularity":
            return Container(name, Container.SINGULARITY,
                             image=f"file://{ROOT/'containers'/'sif'/(name+'.sif')}", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")
    # TODO: one per tool family in YOUR pipeline
    names = ["qc","assembly","map","binning","refine","annot","coverm","r"]
    return {n: c(f"tool-{n}", f"{user}/tool-{n}:{tag}") for n in names}

# ---- transformations (queue + gpu_arg from site; GPU gated by USE_GPU) -----
def make_transformations(ctr):
    def T(name, container, mem_gb=32, cpus=16, gpus=0, runtime=86400):
        t = Transformation(name, site="local", pfn=str(BIN/name), is_stageable=True, container=container)
        for k,v in [("memory",mem_gb*1024),("cores",cpus),("runtime",runtime),("maxwalltime",runtime//60)]:
            t.add_profiles(Namespace.PEGASUS, key=k, value=str(v))
        want_gpu = bool(gpus) and USE_GPU
        t.add_profiles(Namespace.PEGASUS, key="queue",
                       value=SITE["gpu_queue"] if want_gpu else SITE["cpu_queue"])
        if want_gpu:
            t.add_profiles(Namespace.PEGASUS, key="gpus", value=str(gpus))
            if SITE["gpu_arg"]:
                t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=SITE["gpu_arg"])
            t.add_profiles(Namespace.ENV, key="USE_GPU", value="1")
        else:
            if SITE["cpu_arg"]:
                t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=SITE["cpu_arg"])
            t.add_profiles(Namespace.ENV, key="USE_GPU", value="0")   # wrappers run CPU
        return t
    tc = TransformationCatalog()
    tents = {
        # TODO: your jobs. GPU only where it truly helps (DL binners, MMseqs).
        "qc_trim":  T("qc_trim",  ctr["qc"],       mem_gb=16, cpus=16),
        "assembly": T("assembly", ctr["assembly"], mem_gb=120,cpus=64),
        "read_map": T("read_map", ctr["map"],      mem_gb=32, cpus=16),
        "binning":  T("binning",  ctr["binning"],  mem_gb=64, cpus=16, gpus=1),  # GPU
        "refine":   T("refine",   ctr["refine"],   mem_gb=48, cpus=16),
        "annot":    T("annot",    ctr["annot"],    mem_gb=32, cpus=16),
        "abundance":T("abundance",ctr["coverm"],   mem_gb=32, cpus=16),
        "merge":    T("merge",    ctr["r"],        mem_gb=16, cpus=4),
        "predict":  T("predict",  ctr["r"],        mem_gb=16, cpus=4),
    }
    tc.add_transformations(*tents.values())
    seen = {}
    for c in ctr.values():
        if c.name not in seen: tc.add_containers(c); seen[c.name] = True
    return tc, tents

def make_replicas(samples):
    rc = ReplicaCatalog()
    def add(l,p): rc.add_replica("local", l, str(p))
    for m in samples:
        add(f"{m}_R1.fastq.gz", READS/f"{m}_R1.fastq.gz")
        add(f"{m}_R2.fastq.gz", READS/f"{m}_R2.fastq.gz")
    add("gene_list.ref", REF/"gene_list.ref")
    add("metadata.csv",  REF/"metadata.csv")
    return rc

def build_workflow(T, samples):
    wf = Workflow("bioinformatics-workflow")
    gene_ref = File("gene_list.ref"); meta = File("metadata.csv")
    cov_files, hit_files = {}, []
    # ---- per-sample fan-out ----
    for m in samples:
        r1, r2 = File(f"{m}_R1.fastq.gz"), File(f"{m}_R2.fastq.gz")
        t1, t2 = File(f"{m}_t1.fastq.gz"), File(f"{m}_t2.fastq.gz")
        wf.add_jobs(Job(T["qc_trim"], _id=f"qc_{m}").add_args(r1,r2,t1,t2)
                    .add_inputs(r1,r2).add_outputs(t1,t2,stage_out=False,register_replica=False))
        contigs = File(f"{m}_contigs.fasta")
        wf.add_jobs(Job(T["assembly"], _id=f"asm_{m}").add_args(t1,t2,contigs)
                    .add_inputs(t1,t2).add_outputs(contigs,stage_out=False,register_replica=False))
        bam = File(f"{m}.bam"); bai = File(f"{m}.bam.bai")
        wf.add_jobs(Job(T["read_map"], _id=f"map_{m}").add_args(contigs,t1,t2,bam)
                    .add_inputs(contigs,t1,t2).add_outputs(bam,bai,stage_out=False,register_replica=False))
        mags = File(f"{m}_mags.fasta")
        wf.add_jobs(Job(T["binning"], _id=f"bin_{m}").add_args(contigs,bam,bai,mags)
                    .add_inputs(contigs,bam,bai).add_outputs(mags,stage_out=True,register_replica=True))
        cov = File(f"{m}_cov.tsv")
        wf.add_jobs(Job(T["abundance"], _id=f"abund_{m}").add_args(mags,t1,t2,cov)
                    .add_inputs(mags,t1,t2).add_outputs(cov,stage_out=True,register_replica=True))
        cov_files[m] = cov
        ann = File(f"{m}_annot.tsv")
        wf.add_jobs(Job(T["annot"], _id=f"ann_{m}").add_args(mags,ann)
                    .add_inputs(mags).add_outputs(ann,stage_out=True,register_replica=True))
        hits = File(f"{m}_hits.tsv")
        wf.add_jobs(Job(T["refine"], _id=f"hit_{m}").add_args(ann,gene_ref,hits)
                    .add_inputs(ann,gene_ref).add_outputs(hits,stage_out=True,register_replica=True))
        hit_files.append(hits)
    # ---- convergence (once) ----
    integrated = File("integrated.tsv")
    wf.add_jobs(Job(T["merge"], _id="merge").add_args(meta,integrated,*cov_files.values(),*hit_files)
                .add_inputs(meta,*cov_files.values(),*hit_files).add_outputs(integrated,stage_out=True,register_replica=True))
    result = File("result.tsv")
    wf.add_jobs(Job(T["predict"], _id="predict").add_args(integrated,result)
                .add_inputs(integrated).add_outputs(result,stage_out=True,register_replica=True))
    return wf

def make_properties():
    p = Properties()
    p["dagman.retry"] = "3"
    p["pegasus.integrity.checking"] = "none"                        # wrapper edits, no checksum pain
    p["pegasus.transfer.worker.package.autodownload"] = "false"     # containers w/o curl still work
    p["pegasus.transfer.worker.package.strict"] = "false"
    p["dagman.maxjobs"] = os.environ.get("MAXJOBS", "20")
    p["dagman.maxidle"] = "40"
    return p

def detect_samples():
    r1 = sorted(glob.glob(str(READS/"*_R1.fastq.gz")))
    return [os.path.basename(x).replace("_R1.fastq.gz","") for x in r1]

SAMPLES = os.environ.get("SAMPLES","").split() or detect_samples()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    ctr = make_containers(); tc, T = make_transformations(ctr)
    rc = make_replicas(SAMPLES); props = make_properties()
    wf = build_workflow(T, SAMPLES)
    wf.add_transformation_catalog(tc); wf.add_replica_catalog(rc); props.write()
    print(f"workflow | site={PROFILE} gpu={'on' if USE_GPU else 'off'} samples={len(SAMPLES)}")
    pk = dict(submit=not a.plan_only, dir=str(ROOT/"runs"),
              sites=[SITE["exec_site"]], output_sites=["local"])
    wf.plan(**pk)

if __name__ == "__main__":
    main()
