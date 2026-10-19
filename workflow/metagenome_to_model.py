#!/usr/bin/env python3
"""
SubductCR Metagenome-to-Model Workflow  (Pegasus WMS)
=====================================================
End-to-end: raw metagenomes (or existing MAGs) -> MAGs -> annotation ->
metal-gene search -> abundance -> integrate with geochemistry -> predict.

Path A (raw reads):
    qc_trim(fastp) -> assembly(MEGAHIT) -> read_map(Bowtie2) ->
    SemiBin2[GPU] + COMEBin[GPU] + VAMB[GPU] -> refine(DAS Tool) -> refined MAGs
Path B (existing MAGs): skip straight to annotation.
Annotation:  DRAM -> MMseqs2 functional[GPU] -> MMseqs2 metal search[GPU]
Abundance:   CoverM
Integrate:   merge (coverage + metal hits + geochemistry)
Predict:     ML model (GPU if deep-learning)

Defaults (all on for NERSC Perlmutter):
    Shifter backend  = ON
    GPU              = ON
    data folder      = subductcr-final/data/metagenome  (your reads)
    samples          = auto-detected from that folder

Usage:
    python3 workflow/metagenome_to_model.py              # plan + submit
    python3 workflow/metagenome_to_model.py --plan-only  # build DAG only
"""

import os
import glob
import argparse
from pathlib import Path
from Pegasus.api import (
    Workflow, Job, File, Container, Transformation,
    TransformationCatalog, ReplicaCatalog, Properties, Namespace,
)

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
BIN  = ROOT / "bin"
DATA = ROOT / "data"
MAGS = DATA / "mags"
REF  = DATA / "reference"

# your real metagenome reads folder (baked in; override with MAG_READS_DIR)
# metagenome reads folder (confirmed absolute path; override with MAG_READS_DIR)
READS = Path(os.environ.get(
    "MAG_READS_DIR",
    "/home/hsafri/hotSprings/PegasusWMS-SubductCR_16S-diversity/subductcr-final/data/metagenome",
))


# --------------------------------------------------------------------------
# containers  (one image per tool family)
# --------------------------------------------------------------------------
def make_containers():
    """Return the tool containers. Shifter is the default backend."""
    shifter = os.environ.get("MAG_USE_SHIFTER", "1") == "1"
    sif     = os.environ.get("MAG_USE_SIF", "0") == "1"
    user    = os.environ.get("MAG_DOCKER_USER", "swarmourr")
    tag     = os.environ.get("MAG_TAG", "latest")

    def container(name, image):
        if shifter:
            return Container(name, Container.SHIFTER,
                             image=f"shifter:///{image}", bypass_staging=True)
        if sif:
            path = ROOT / "containers" / "sif" / f"{name}.sif"
            return Container(name, Container.SINGULARITY,
                             image=f"file://{path}", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")

    names = ["qc", "assembly", "map", "semibin", "comebin", "vamb",
             "refine", "dram", "mmseqs", "coverm", "r"]
    return {n: container(f"mag-{n}", f"{user}/mag-{n}:{tag}") for n in names}


# --------------------------------------------------------------------------
# transformations  (bin/ scripts -> Pegasus jobs; GPU jobs -> GPU nodes)
# --------------------------------------------------------------------------
# GPU toggle: MAG_GPU=1 (default) uses GPU nodes for the DL/MMseqs jobs;
# MAG_GPU=0 runs everything on CPU (slower, but no GPU containers/queues needed).
USE_GPU = os.environ.get("MAG_GPU", "1") == "1"

def make_transformations(ctr):
    def T(name, container, mem_gb=32, cpus=16, gpus=0, runtime=86400, queue="regular"):
        t = Transformation(name, site="local",
                            pfn=str(BIN / name), is_stageable=True,
                            container=container)
        t.add_profiles(Namespace.PEGASUS, key="memory",      value=str(mem_gb * 1024))
        t.add_profiles(Namespace.PEGASUS, key="cores",       value=str(cpus))
        t.add_profiles(Namespace.PEGASUS, key="runtime",     value=str(runtime))
        t.add_profiles(Namespace.PEGASUS, key="maxwalltime", value=str(runtime // 60))
        t.add_profiles(Namespace.PEGASUS, key="queue",       value=queue)
        if gpus and USE_GPU:
            t.add_profiles(Namespace.PEGASUS, key="gpus", value=str(gpus))
            t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value="-C gpu")
        else:
            t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value="-C cpu")
        return t

    tc = TransformationCatalog()
    tents = {
        # ---- Path A: raw reads -> MAGs ----
        "qc_trim":      T("qc_trim",      ctr["qc"],       mem_gb=16,  cpus=16, queue="regular"),
        "assembly":     T("assembly",     ctr["assembly"], mem_gb=120, cpus=64),              # MEGAHIT (CPU)
        "read_map":     T("read_map",     ctr["map"],      mem_gb=32,  cpus=16),              # Bowtie2 (CPU)
        "bin_semibin":  T("bin_semibin",  ctr["semibin"],  mem_gb=64,  cpus=16, gpus=1),      # GPU
        "bin_comebin":  T("bin_comebin",  ctr["comebin"],  mem_gb=64,  cpus=16, gpus=1),      # GPU
        "bin_vamb":     T("bin_vamb",     ctr["vamb"],     mem_gb=64,  cpus=16, gpus=1),      # GPU
        "refine":       T("refine",       ctr["refine"],   mem_gb=48,  cpus=16),              # DAS Tool (CPU)
        # ---- Annotation ----
        "dram":         T("dram",         ctr["dram"],     mem_gb=64,  cpus=16),              # DRAM (CPU)
        "mmseqs_func":  T("mmseqs_func",  ctr["mmseqs"],   mem_gb=48,  cpus=16, gpus=1),      # GPU
        "mmseqs_metal": T("mmseqs_metal", ctr["mmseqs"],   mem_gb=16,  cpus=4),               # CPU (KO match)
        # ---- Abundance ----
        "abundance":    T("abundance",    ctr["coverm"],   mem_gb=32,  cpus=16),              # CoverM (CPU)
        # ---- Integrate + predict ----
        "merge":        T("merge",        ctr["r"],        mem_gb=16,  cpus=4, queue="regular"),
        "predict":      T("predict",      ctr["r"],        mem_gb=16,  cpus=4),               # CPU (R model)
    }
    tc.add_transformations(*tents.values())

    seen = {}
    for c in ctr.values():
        if c.name not in seen:
            tc.add_containers(c)
            seen[c.name] = True
    return tc, tents


# --------------------------------------------------------------------------
# replica catalog  (where every input file lives)
# --------------------------------------------------------------------------
def make_replicas(metagenomes, existing_mags):
    rc = ReplicaCatalog()

    def add(lfn, path):
        rc.add_replica("local", lfn, str(path))

    for m in metagenomes:
        add(f"{m}_R1.fastq.gz", READS / f"{m}_R1.fastq.gz")
        add(f"{m}_R2.fastq.gz", READS / f"{m}_R2.fastq.gz")
    for mag in existing_mags:
        add(f"{mag}.fasta", MAGS / f"{mag}.fasta")
    add("metal_genes.ref",  REF / "metal_genes.ref")
    add("geochemistry.csv", REF / "geochemistry.csv")
    return rc


# --------------------------------------------------------------------------
# the workflow  (inputs -> jobs -> outputs)
# --------------------------------------------------------------------------
def build_workflow(T, metagenomes, existing_mags):
    wf = Workflow("subductcr-metagenome-to-model")
    metal_ref = File("metal_genes.ref")
    geochem   = File("geochemistry.csv")

    mag_files      = {m: File(f"{m}.fasta") for m in existing_mags}
    mags_for_annot = list(existing_mags)
    coverage_files = {}

    # ===== Path A: per metagenome, raw reads -> refined MAGs =====
    for m in metagenomes:
        r1 = File(f"{m}_R1.fastq.gz")
        r2 = File(f"{m}_R2.fastq.gz")

        # qc trim (fastp)
        t1 = File(f"{m}_trim_R1.fastq.gz")
        t2 = File(f"{m}_trim_R2.fastq.gz")
        wf.add_jobs(Job(T["qc_trim"], _id=f"qc_{m}")
                    .add_args(r1, r2, t1, t2)
                    .add_inputs(r1, r2)
                    .add_outputs(t1, t2, stage_out=False, register_replica=False))

        # assembly (MEGAHIT)
        contigs = File(f"{m}_contigs.fasta")
        wf.add_jobs(Job(T["assembly"], _id=f"assembly_{m}")
                    .add_args(t1, t2, contigs)
                    .add_inputs(t1, t2)
                    .add_outputs(contigs, stage_out=False, register_replica=False))

        # read mapping (Bowtie2) -> sorted bam
        bam = File(f"{m}_sorted.bam")
        wf.add_jobs(Job(T["read_map"], _id=f"map_{m}")
                    .add_args(contigs, t1, t2, bam)
                    .add_inputs(contigs, t1, t2)
                    .add_outputs(bam, stage_out=False, register_replica=False))

        # three binners (GPU)
        sb = File(f"{m}_bins_semibin.tar")
        cb = File(f"{m}_bins_comebin.tar")
        vb = File(f"{m}_bins_vamb.tar")
        wf.add_jobs(Job(T["bin_semibin"], _id=f"semibin_{m}")
                    .add_args(contigs, bam, sb)
                    .add_inputs(contigs, bam)
                    .add_outputs(sb, stage_out=False, register_replica=False))
        wf.add_jobs(Job(T["bin_comebin"], _id=f"comebin_{m}")
                    .add_args(contigs, bam, cb)
                    .add_inputs(contigs, bam)
                    .add_outputs(cb, stage_out=False, register_replica=False))
        wf.add_jobs(Job(T["bin_vamb"], _id=f"vamb_{m}")
                    .add_args(contigs, bam, vb)
                    .add_inputs(contigs, bam)
                    .add_outputs(vb, stage_out=False, register_replica=False))

        # refinement (DAS Tool) -> refined MAGs
        refined = File(f"{m}_mags.fasta")
        wf.add_jobs(Job(T["refine"], _id=f"refine_{m}")
                    .add_args(contigs, sb, cb, vb, refined)
                    .add_inputs(contigs, sb, cb, vb)
                    .add_outputs(refined, stage_out=True, register_replica=True))

        # abundance (CoverM) -> coverage
        cov = File(f"{m}_coverage.tsv")
        wf.add_jobs(Job(T["abundance"], _id=f"abund_{m}")
                    .add_args(refined, t1, t2, cov)
                    .add_inputs(refined, t1, t2)
                    .add_outputs(cov, stage_out=True, register_replica=True))
        coverage_files[m] = cov

        # the new MAGs join Path A's annotation
        mag_files[f"{m}_new"] = refined
        mags_for_annot.append(f"{m}_new")

    # ===== Annotation: per MAG set, DRAM -> MMseqs2 functional -> metal search =====
    metal_hits = []
    for mag in mags_for_annot:
        mf = mag_files[mag]

        # DRAM annotation -> KO numbers (this is what we match metal genes against)
        ann = File(f"{mag}_dram.tsv")
        wf.add_jobs(Job(T["dram"], _id=f"dram_{mag}")
                    .add_args(mf, ann)
                    .add_inputs(mf)
                    .add_outputs(ann, stage_out=True, register_replica=True))

        # MMseqs2 UniRef50 search -> general functional annotation (kept for completeness)
        func = File(f"{mag}_functional.tsv")
        wf.add_jobs(Job(T["mmseqs_func"], _id=f"func_{mag}")
                    .add_args(mf, func)
                    .add_inputs(mf)
                    .add_outputs(func, stage_out=True, register_replica=True))

        # metal-gene filter: match DRAM's KO output against metal_genes.ref (KO vs KO)
        hits = File(f"{mag}_metal_hits.tsv")
        wf.add_jobs(Job(T["mmseqs_metal"], _id=f"metal_{mag}")
                    .add_args(ann, metal_ref, hits)
                    .add_inputs(ann, metal_ref)
                    .add_outputs(hits, stage_out=True, register_replica=True))
        metal_hits.append(hits)

    # ===== Integrate: merge coverage + metal hits + geochemistry =====
    integrated = File("integrated_table.tsv")
    merge_inputs = list(coverage_files.values()) + metal_hits
    wf.add_jobs(Job(T["merge"], _id="merge")
                .add_args(geochem, integrated, *merge_inputs)
                .add_inputs(geochem, *merge_inputs)
                .add_outputs(integrated, stage_out=True, register_replica=True))

    # ===== Predict metal potential =====
    results = File("metal_prediction.tsv")
    wf.add_jobs(Job(T["predict"], _id="predict")
                .add_args(integrated, results)
                .add_inputs(integrated)
                .add_outputs(results, stage_out=True, register_replica=True))

    return wf


# --------------------------------------------------------------------------
# properties
# --------------------------------------------------------------------------
def make_properties():
    p = Properties()
    p["dagman.retry"] = "3"
    p["pegasus.integrity.checking"] = "none"
    # containers lack curl/wget — don't re-download the worker package inside
    # them; use the one already staged. Fixes "Unable to find curl/wget".
    p["pegasus.transfer.worker.package"] = "true"
    p["pegasus.transfer.worker.package.autodownload"] = "false"
    p["pegasus.transfer.worker.package.strict"] = "false"
    p["dagman.maxjobs"] = os.environ.get("MAG_MAXJOBS", "20")
    p["dagman.maxidle"] = "40"
    if os.environ.get("MAG_USE_SHIFTER", "1") != "1":
        p["pegasus.data.configuration"] = "condorio"
    return p


# --------------------------------------------------------------------------
# sample list  (auto-detect from the reads folder; fall back to the 34)
# --------------------------------------------------------------------------
DEFAULT_SAMPLES = (
    "ARS BQF BQS BR1F BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETS FAS "
    "MTF PBS PFF PFS PGF PGS PLS QH2F QHS2 QNF QNS RSF RSS RVF SIF SIS SLF SLS TCF TCS"
)

def detect_samples():
    r1 = sorted(glob.glob(str(READS / "*_R1.fastq.gz")))
    names = [os.path.basename(x).replace("_R1.fastq.gz", "") for x in r1]
    return names if names else DEFAULT_SAMPLES.split()

METAGENOMES   = os.environ.get("MAG_METAGENOMES", "").split() or detect_samples()
EXISTING_MAGS = os.environ.get("MAG_EXISTING", "").split()


# --------------------------------------------------------------------------
# default environment (Shifter + GPU on by default)
# --------------------------------------------------------------------------
_DEFAULTS = {
    "MAG_USE_SHIFTER":  "1",          # Shifter backend ON
    "MAG_GPU":          "1",          # GPU ON (SemiBin2/COMEBin/VAMB/MMseqs2/predict)
    "MAG_TAG":          "latest",
    "RESOURCE_PROJECT": "m4144",
    "RESOURCE_USERNAME":"hsafri",
    "RESOURCE_SCRATCH_DIR": os.environ.get("PSCRATCH", "/pscratch/sd/h/hsafri"),
    "SSH_PRIVATE_KEY":  os.path.expanduser("~/.ssh/nersc"),
}
for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="SubductCR Metagenome-to-Model workflow")
    ap.add_argument("--plan-only", action="store_true",
                    help="build and plan the DAG but do not submit")
    args = ap.parse_args()

    ctr          = make_containers()
    tc, T        = make_transformations(ctr)
    rc           = make_replicas(METAGENOMES, EXISTING_MAGS)
    props        = make_properties()
    wf           = build_workflow(T, METAGENOMES, EXISTING_MAGS)

    wf.add_transformation_catalog(tc)
    wf.add_replica_catalog(rc)
    props.write()

    on_nersc  = os.environ.get("MAG_USE_SHIFTER", "1") == "1"
    exec_site = os.environ.get("MAG_SITE", "compute" if on_nersc else "local")

    print("SubductCR Metagenome-to-Model workflow")
    print(f"  backend        : {'Shifter' if on_nersc else 'Docker/SIF'}")
    print(f"  GPU            : {'ON' if os.environ.get('MAG_GPU')=='1' else 'OFF'}")
    print(f"  reads folder   : {READS}")
    print(f"  Path A         : {len(METAGENOMES)} metagenomes")
    print(f"  Path B         : {len(EXISTING_MAGS)} existing MAGs")
    print(f"  GPU jobs       : SemiBin2, COMEBin, VAMB, MMseqs2 (func+metal), predict")
    print(f"  execution site : {exec_site}")

    plan_kwargs = dict(submit=not args.plan_only, dir=str(ROOT / "runs"))
    if on_nersc:
        plan_kwargs.update(sites=[exec_site], output_sites=["local"])
    wf.plan(**plan_kwargs)


if __name__ == "__main__":
    main()
