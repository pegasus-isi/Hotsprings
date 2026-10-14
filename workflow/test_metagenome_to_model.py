#!/usr/bin/env python3
"""
TEST Metagenome-to-Model Workflow  (Pegasus WMS)
================================================
A small, fast end-to-end test of the full pipeline on 2-3 samples with
subsampled reads — to verify every step works before committing to all 35.

Same structure as the full workflow, but:
  - only 3 samples (override with MAG_TEST_SAMPLES)
  - reads are subsampled to ~500k read pairs (quick assembly)
  - smaller memory / shorter runtime
  - GPU still used for the deep-learning + MMseqs2 steps

Usage:
  python3 workflow/test_metagenome_to_model.py --plan-only   # check the DAG
  python3 workflow/test_metagenome_to_model.py               # run the test
"""
import os, glob, argparse
from pathlib import Path
from Pegasus.api import (Workflow, Job, File, Container, Transformation,
    TransformationCatalog, ReplicaCatalog, Properties, Namespace)

ROOT = Path(__file__).resolve().parent.parent
BIN  = ROOT / "bin"
DATA = ROOT / "data"
MAGS = DATA / "mags"
REF  = DATA / "reference"
# metagenome reads folder (confirmed absolute path; override with MAG_READS_DIR)
READS = Path(os.environ.get(
    "MAG_READS_DIR",
    "/home/hsafri/hotSprings/PegasusWMS-SubductCR_16S-diversity/subductcr-final/data/metagenome",
))

# --- TEST: pick a few samples that have matching geochemistry ---
TEST_SAMPLES = os.environ.get("MAG_TEST_SAMPLES", "CYF SLS TCF").split()
SUBSAMPLE = os.environ.get("MAG_SUBSAMPLE", "500000")   # read pairs to keep


def make_containers():
    shifter = os.environ.get("MAG_USE_SHIFTER", "1") == "1"
    user = os.environ.get("MAG_DOCKER_USER", "swarmourr")
    tag  = os.environ.get("MAG_TAG", "latest")
    def c(name, image):
        if shifter:
            return Container(name, Container.SHIFTER, image=f"shifter:///{image}", bypass_staging=True)
        return Container(name, Container.DOCKER, image=f"docker://{image}")
    names = ["qc","assembly","map","semibin","comebin","vamb","refine","dram","mmseqs","coverm","r"]
    return {n: c(f"mag-{n}", f"{user}/mag-{n}:{tag}") for n in names}


def make_transformations(ctr):
    # TEST: smaller memory, shorter runtime (12h), shared queue where possible
    def T(name, container, mem_gb=16, cpus=8, gpus=0, runtime=43200, queue="shared"):
        t = Transformation(name, site="local", pfn=str(BIN / name),
                            is_stageable=True, container=container)
        t.add_profiles(Namespace.PEGASUS, key="memory",      value=str(mem_gb*1024))
        t.add_profiles(Namespace.PEGASUS, key="cores",       value=str(cpus))
        t.add_profiles(Namespace.PEGASUS, key="runtime",     value=str(runtime))
        t.add_profiles(Namespace.PEGASUS, key="maxwalltime", value=str(runtime//60))
        t.add_profiles(Namespace.PEGASUS, key="queue",       value=queue)
        if gpus:
            t.add_profiles(Namespace.PEGASUS, key="gpus", value=str(gpus))
            t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value="-C gpu")
        else:
            t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value="-C cpu")
        return t
    tc = TransformationCatalog()
    tents = {
        "subsample":    T("subsample",   ctr["qc"],       mem_gb=8,  cpus=4),
        "qc_trim":      T("qc_trim",      ctr["qc"],       mem_gb=8,  cpus=8),
        "assembly":     T("assembly",     ctr["assembly"], mem_gb=32, cpus=16),
        "read_map":     T("read_map",     ctr["map"],      mem_gb=16, cpus=8),
        "bin_semibin":  T("bin_semibin",  ctr["semibin"],  mem_gb=32, cpus=8, gpus=1, queue="regular"),
        "bin_comebin":  T("bin_comebin",  ctr["comebin"],  mem_gb=32, cpus=8, gpus=1, queue="regular"),
        "bin_vamb":     T("bin_vamb",     ctr["vamb"],     mem_gb=32, cpus=8, gpus=1, queue="regular"),
        "refine":       T("refine",       ctr["refine"],   mem_gb=16, cpus=8),
        "dram":         T("dram",         ctr["dram"],     mem_gb=16, cpus=8),
        "mmseqs_func":  T("mmseqs_func",  ctr["mmseqs"],   mem_gb=24, cpus=8, gpus=1, queue="regular"),
        "mmseqs_metal": T("mmseqs_metal", ctr["mmseqs"],   mem_gb=16, cpus=8),
        "abundance":    T("abundance",    ctr["coverm"],   mem_gb=16, cpus=8),
        "merge":        T("merge",        ctr["r"],        mem_gb=8,  cpus=2),
        "predict":      T("predict",      ctr["r"],        mem_gb=8,  cpus=2),
    }
    tc.add_transformations(*tents.values())
    seen = {}
    for c in ctr.values():
        if c.name not in seen:
            tc.add_containers(c); seen[c.name] = True
    return tc, tents


def make_replicas(samples):
    rc = ReplicaCatalog()
    def add(l, p): rc.add_replica("local", l, str(p))
    for m in samples:
        add(f"{m}_R1.fastq.gz", READS / f"{m}_R1.fastq.gz")
        add(f"{m}_R2.fastq.gz", READS / f"{m}_R2.fastq.gz")
    add("metal_genes.ref",  REF / "metal_genes.ref")
    add("geochemistry.csv", REF / "geochemistry.csv")
    return rc


def build_workflow(T, samples):
    wf = Workflow("test-metagenome-to-model")
    metal_ref = File("metal_genes.ref")
    geochem   = File("geochemistry.csv")
    mag_files = {}
    mags_for_annot = []
    coverage_files = {}

    for m in samples:
        r1 = File(f"{m}_R1.fastq.gz"); r2 = File(f"{m}_R2.fastq.gz")

        # TEST: subsample the reads first (fast assembly)
        s1 = File(f"{m}_sub_R1.fastq.gz"); s2 = File(f"{m}_sub_R2.fastq.gz")
        wf.add_jobs(Job(T["subsample"], _id=f"sub_{m}")
                    .add_args(r1, r2, s1, s2)
                    .add_inputs(r1, r2)
                    .add_outputs(s1, s2, stage_out=False, register_replica=False))

        t1 = File(f"{m}_trim_R1.fastq.gz"); t2 = File(f"{m}_trim_R2.fastq.gz")
        wf.add_jobs(Job(T["qc_trim"], _id=f"qc_{m}")
                    .add_args(s1, s2, t1, t2)
                    .add_inputs(s1, s2)
                    .add_outputs(t1, t2, stage_out=False, register_replica=False))

        contigs = File(f"{m}_contigs.fasta")
        wf.add_jobs(Job(T["assembly"], _id=f"assembly_{m}")
                    .add_args(t1, t2, contigs)
                    .add_inputs(t1, t2)
                    .add_outputs(contigs, stage_out=True, register_replica=True))

        bam = File(f"{m}_sorted.bam")
        wf.add_jobs(Job(T["read_map"], _id=f"map_{m}")
                    .add_args(contigs, t1, t2, bam)
                    .add_inputs(contigs, t1, t2)
                    .add_outputs(bam, stage_out=False, register_replica=False))

        sb = File(f"{m}_bins_semibin.tar"); cb = File(f"{m}_bins_comebin.tar"); vb = File(f"{m}_bins_vamb.tar")
        wf.add_jobs(Job(T["bin_semibin"], _id=f"semibin_{m}").add_args(contigs, bam, sb)
                    .add_inputs(contigs, bam).add_outputs(sb, stage_out=False, register_replica=False))
        wf.add_jobs(Job(T["bin_comebin"], _id=f"comebin_{m}").add_args(contigs, bam, cb)
                    .add_inputs(contigs, bam).add_outputs(cb, stage_out=False, register_replica=False))
        wf.add_jobs(Job(T["bin_vamb"], _id=f"vamb_{m}").add_args(contigs, bam, vb)
                    .add_inputs(contigs, bam).add_outputs(vb, stage_out=False, register_replica=False))

        refined = File(f"{m}_mags.fasta")
        wf.add_jobs(Job(T["refine"], _id=f"refine_{m}")
                    .add_args(contigs, sb, cb, vb, refined)
                    .add_inputs(contigs, sb, cb, vb)
                    .add_outputs(refined, stage_out=True, register_replica=True))

        cov = File(f"{m}_coverage.tsv")
        wf.add_jobs(Job(T["abundance"], _id=f"abund_{m}")
                    .add_args(refined, t1, t2, cov)
                    .add_inputs(refined, t1, t2)
                    .add_outputs(cov, stage_out=True, register_replica=True))
        coverage_files[m] = cov
        mag_files[f"{m}_new"] = refined
        mags_for_annot.append(f"{m}_new")

    metal_hits = []
    for mag in mags_for_annot:
        mf = mag_files[mag]
        ann = File(f"{mag}_dram.tsv")
        wf.add_jobs(Job(T["dram"], _id=f"dram_{mag}").add_args(mf, ann)
                    .add_inputs(mf).add_outputs(ann, stage_out=True, register_replica=True))
        func = File(f"{mag}_functional.tsv")
        wf.add_jobs(Job(T["mmseqs_func"], _id=f"func_{mag}").add_args(mf, func)
                    .add_inputs(mf).add_outputs(func, stage_out=True, register_replica=True))
        hits = File(f"{mag}_metal_hits.tsv")
        wf.add_jobs(Job(T["mmseqs_metal"], _id=f"metal_{mag}").add_args(ann, metal_ref, hits)
                    .add_inputs(ann, metal_ref).add_outputs(hits, stage_out=True, register_replica=True))
        metal_hits.append(hits)

    integrated = File("integrated_table.tsv")
    merge_in = list(coverage_files.values()) + metal_hits
    wf.add_jobs(Job(T["merge"], _id="merge").add_args(geochem, integrated, *merge_in)
                .add_inputs(geochem, *merge_in).add_outputs(integrated, stage_out=True, register_replica=True))

    results = File("metal_prediction.tsv")
    wf.add_jobs(Job(T["predict"], _id="predict").add_args(integrated, results)
                .add_inputs(integrated).add_outputs(results, stage_out=True, register_replica=True))
    return wf


def make_properties():
    p = Properties()
    p["dagman.retry"] = "2"
    p["pegasus.integrity.checking"] = "none"
    p["dagman.maxjobs"] = "10"
    p["dagman.maxidle"] = "20"
    return p


for _k, _v in {"MAG_USE_SHIFTER":"1","MAG_GPU":"1","MAG_TAG":"latest",
               "RESOURCE_PROJECT":"m4144","RESOURCE_USERNAME":"hsafri",
               "RESOURCE_SCRATCH_DIR":os.environ.get("PSCRATCH","/pscratch/sd/h/hsafri"),
               "SSH_PRIVATE_KEY":os.path.expanduser("~/.ssh/nersc")}.items():
    os.environ.setdefault(_k, _v)


def main():
    ap = argparse.ArgumentParser(description="TEST metagenome-to-model (small, fast)")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()

    ctr   = make_containers()
    tc, T = make_transformations(ctr)
    rc    = make_replicas(TEST_SAMPLES)
    props = make_properties()
    wf    = build_workflow(T, TEST_SAMPLES)

    wf.add_transformation_catalog(tc)
    wf.add_replica_catalog(rc)
    props.write()

    print("TEST Metagenome-to-Model workflow (small, fast)")
    print(f"  samples    : {TEST_SAMPLES}  (subsampled to {SUBSAMPLE} pairs)")
    print(f"  reads from : {READS}")
    print(f"  GPU        : {'ON' if os.environ.get('MAG_GPU')=='1' else 'OFF'}")
    print(f"  purpose    : verify every step end-to-end before scaling to all 35")

    pk = dict(submit=not args.plan_only, dir=str(ROOT / "runs"))
    pk.update(sites=["compute"], output_sites=["local"])
    wf.plan(**pk)


if __name__ == "__main__":
    main()
