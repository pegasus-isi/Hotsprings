#!/usr/bin/env python3
"""
SubductCR end-to-end workflow  (Pegasus WMS)
============================================

Rebuilds the Fullerton et al. 2021 hot-springs analysis from public data:

    16S track :  KEBJ01 processed sequences  -->  ASVs  -->  community analysis
    MG  track :  ENA metagenome reads         -->  enzymes -->  gene analysis
    both      -->  integrate with geochemistry  -->  figures + report

Design goals: one file, readable, no clever tricks. Every job is a small
wrapper script in bin/; this generator just wires inputs -> jobs -> outputs.

Backends (pick one, default = Docker Hub images):
    SUBDUCTCR_USE_SIF=1       use local Singularity .sif images  (ACCESS)
    SUBDUCTCR_USE_SHIFTER=1   use Shifter images                 (NERSC Perlmutter)

Usage:
    python3 workflow/end_to_end.py                # plan + submit
    python3 workflow/end_to_end.py --plan-only    # build the DAG, don't submit
"""

import os
import argparse
from pathlib import Path
from Pegasus.api import (
    Workflow, Job, File, Container, Transformation, TransformationCatalog,
    ReplicaCatalog, Properties, Namespace,
)

# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------
ROOT   = Path(__file__).resolve().parent.parent
BIN    = ROOT / "bin"
DATA   = ROOT / "data"
REF    = DATA / "reference"
S16    = DATA / "16s"
MG     = DATA / "metagenome"
CONFIG = ROOT / "config"


# --------------------------------------------------------------------------
# containers  (one image per tool family)
# --------------------------------------------------------------------------
def make_containers():
    """Return the three containers, honoring the backend env vars."""
    shifter = os.environ.get("SUBDUCTCR_USE_SHIFTER", "0") == "1"
    sif     = os.environ.get("SUBDUCTCR_USE_SIF", "0") == "1"

    def container(name, image):
        if shifter:
            return Container(name, Container.SHIFTER,
                             image=f"shifter://{image}", bypass_staging=True)
        if sif:
            path = ROOT / "containers" / "sif" / f"{name}.sif"
            return Container(name, Container.SINGULARITY,
                             image=f"file://{path}", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")

    return {
        "r":       container("subductcr-r",       "swarmourr/subductcr-r:1.0"),
        "mothur":  container("subductcr-mothur",  "swarmourr/subductcr-mothur:1.0"),
        "mifaser": container("subductcr-mifaser", "swarmourr/subductcr-mifaser:1.0"),
    }


# --------------------------------------------------------------------------
# transformations  (bin/ scripts -> Pegasus jobs)
# --------------------------------------------------------------------------
def make_transformations(ctr):
    """One Transformation per wrapper in bin/. mem/cpus kept modest & explicit."""
    def T(name, container, mem_gb=4, cpus=1):
        t = Transformation(name, site="local",
                           pfn=str(BIN / name), is_stageable=True,
                           container=container)
        t.add_profiles(Namespace.PEGASUS, key="memory",  value=str(mem_gb * 1024))
        t.add_profiles(Namespace.PEGASUS, key="cores",   value=str(cpus))
        return t

    tc = TransformationCatalog()
    tents = {
        # 16S track
        "mothur_asv":       T("mothur_asv",       ctr["mothur"], mem_gb=32, cpus=8),
        "filter_normalize": T("filter_normalize", ctr["r"]),
        "asv_network":      T("asv_network",      ctr["r"]),
        "nmds_adonis":      T("nmds_adonis",      ctr["r"]),
        "clique_geochem":   T("clique_geochem",   ctr["r"]),
        # metagenome track
        "trim_reads":       T("trim_reads",       ctr["mothur"], mem_gb=8, cpus=4),
        "mifaser":          T("mifaser",          ctr["mifaser"], mem_gb=16, cpus=8),
        "gene_merge":       T("gene_merge",       ctr["r"]),
        "gene_network":     T("gene_network",     ctr["r"]),
        "gene_geochem":     T("gene_geochem",     ctr["r"]),
        "carbon_flux":      T("carbon_flux",      ctr["r"]),
        # shared
        "make_report":      T("make_report",      ctr["r"]),
    }
    tc.add_transformations(*tents.values())
    # register the containers in the catalog too, otherwise the transformations
    # reference containers Pegasus doesn't know about ("non existent container").
    seen = {}
    for c in ctr.values():
        if c.name not in seen:
            tc.add_containers(c); seen[c.name] = True
    return tc, tents


# --------------------------------------------------------------------------
# replica catalog  (declare where every input file physically lives)
# --------------------------------------------------------------------------
def make_replicas(mg_samples):
    rc = ReplicaCatalog()

    def add(lfn, path):
        rc.add_replica("local", lfn, str(path))

    # 16S inputs
    add("kebj01_16s.fasta",   S16 / "kebj01_16s.fasta")          # processed 16S seqs
    add("silva_v132.db",      REF / "silva_v132.db")             # mothur SILVA ref
    add("silva_v132.tax",     REF / "silva_v132.tax")
    # metagenome reads (per sample, paired)
    for s in mg_samples:
        add(f"{s}_R1.fastq.gz", MG / f"{s}_R1.fastq.gz")
        add(f"{s}_R2.fastq.gz", MG / f"{s}_R2.fastq.gz")
    add("ec_carbon.csv",      REF / "ec_carbon.csv")             # carbon-fixation ECs
    # environmental / parameters
    add("geochem.csv",        REF / "geochem.csv")               # site geochemistry (+ Suppl.)
    add("cell_counts.csv",    REF / "cell_counts.csv")           # Suppl. Table S4
    add("flux_params.yml",    CONFIG / "flux_params.yml")
    return rc


# --------------------------------------------------------------------------
# the workflow  (inputs -> jobs -> outputs)
# --------------------------------------------------------------------------
def build_workflow(T, mg_samples):
    wf = Workflow("subductcr-end-to-end")

    # ---- shared input files ----
    silva_db  = File("silva_v132.db");  silva_tax = File("silva_v132.tax")
    geochem   = File("geochem.csv");    cells     = File("cell_counts.csv")
    flux_par  = File("flux_params.yml"); ec_carbon = File("ec_carbon.csv")

    # ======================================================================
    # 16S track :  KEBJ01 sequences -> ASVs -> community structure
    # ======================================================================
    kebj      = File("kebj01_16s.fasta")
    asv_table = File("asv_table.tsv"); taxonomy = File("taxonomy.tsv")

    # SILVA is used DIRECTLY from mothur (no separate trimming job).
    j_asv = (Job(T["mothur_asv"], _id="mothur_asv")
             .add_args(kebj, silva_db, silva_tax, asv_table, taxonomy)
             .add_inputs(kebj, silva_db, silva_tax)
             .add_outputs(asv_table, taxonomy, stage_out=True, register_replica=True))

    filtered = File("filtered.rds")
    j_filt = (Job(T["filter_normalize"], _id="filter_normalize")
              .add_args(asv_table, taxonomy, filtered)
              .add_inputs(asv_table, taxonomy)
              .add_outputs(filtered, stage_out=True, register_replica=True))

    asv_cliques = File("asv_cliques.rds")
    j_net = (Job(T["asv_network"], _id="asv_network")
             .add_args(filtered, asv_cliques)
             .add_inputs(filtered)
             .add_outputs(asv_cliques, stage_out=True, register_replica=True))

    nmds = File("nmds.tsv"); adonis = File("adonis.tsv"); fig2 = File("fig2.pdf")
    j_nmds = (Job(T["nmds_adonis"], _id="nmds_adonis")
              .add_args(filtered, geochem, nmds, adonis, fig2)
              .add_inputs(filtered, geochem)
              .add_outputs(nmds, adonis, fig2, stage_out=True, register_replica=True))

    asv_env = File("asv_clique_env.tsv")
    j_cg = (Job(T["clique_geochem"], _id="clique_geochem")
            .add_args(asv_cliques, geochem, asv_env)
            .add_inputs(asv_cliques, geochem)
            .add_outputs(asv_env, stage_out=True, register_replica=True))

    # ======================================================================
    # metagenome track :  ENA reads -> enzymes -> gene structure
    # ======================================================================
    enzyme_files = []
    for s in mg_samples:
        r1 = File(f"{s}_R1.fastq.gz"); r2 = File(f"{s}_R2.fastq.gz")
        t1 = File(f"{s}_trim_R1.fastq.gz"); t2 = File(f"{s}_trim_R2.fastq.gz")
        wf.add_jobs(Job(T["trim_reads"], _id=f"trim_{s}")
                    .add_args(r1, r2, t1, t2)
                    .add_inputs(r1, r2)
                    .add_outputs(t1, t2, stage_out=False, register_replica=False))
        enz = File(f"{s}_enzymes.tsv")
        wf.add_jobs(Job(T["mifaser"], _id=f"mifaser_{s}")
                    .add_args(t1, t2, enz)
                    .add_inputs(t1, t2)
                    .add_outputs(enz, stage_out=False, register_replica=False))
        enzyme_files.append(enz)

    gene_table = File("gene_table.tsv")
    j_gmerge = (Job(T["gene_merge"], _id="gene_merge")
                .add_args(ec_carbon, gene_table, *enzyme_files)
                .add_inputs(ec_carbon, *enzyme_files)
                .add_outputs(gene_table, stage_out=True, register_replica=True))

    gene_cliques = File("gene_cliques.rds")
    j_gnet = (Job(T["gene_network"], _id="gene_network")
              .add_args(gene_table, gene_cliques)
              .add_inputs(gene_table)
              .add_outputs(gene_cliques, stage_out=True, register_replica=True))

    gene_env = File("gene_clique_env.tsv")
    j_gg = (Job(T["gene_geochem"], _id="gene_geochem")
            .add_args(gene_cliques, geochem, gene_env)
            .add_inputs(gene_cliques, geochem)
            .add_outputs(gene_env, stage_out=True, register_replica=True))

    carbon = File("carbon_flux.tsv")
    j_flux = (Job(T["carbon_flux"], _id="carbon_flux")
              .add_args(geochem, cells, flux_par, carbon)
              .add_inputs(geochem, cells, flux_par)
              .add_outputs(carbon, stage_out=True, register_replica=True))

    # ======================================================================
    # report :  bring both tracks together
    # ======================================================================
    report = File("report.html")
    j_rep = (Job(T["make_report"], _id="make_report")
             .add_args(asv_env, gene_env, nmds, adonis, carbon, report)
             .add_inputs(asv_env, gene_env, nmds, adonis, carbon)
             .add_outputs(report, stage_out=True, register_replica=True))

    wf.add_jobs(j_asv, j_filt, j_net, j_nmds, j_cg,
                j_gmerge, j_gnet, j_gg, j_flux, j_rep)
    return wf


# --------------------------------------------------------------------------
# properties
# --------------------------------------------------------------------------
def make_properties():
    # Keep this minimal. On NERSC the environment (system .pegasusrc) provides
    # the site catalog and the right data configuration for the compute site,
    # so we do NOT set data.configuration or a site catalog here — overriding
    # them is what breaks the normal "-e compute" behavior.
    p = Properties()
    p["dagman.retry"] = "3"
    if os.environ.get("SUBDUCTCR_USE_SHIFTER", "0") != "1":
        # only for local/Docker runs
        p["pegasus.data.configuration"] = "condorio"
    return p


# --------------------------------------------------------------------------
# sample list  (35 metagenome libraries retrievable from ENA)
# --------------------------------------------------------------------------
MG_SAMPLES = [
    "ARS", "BQF", "BQS", "BR1F", "BRF2", "BRS1", "BRS2", "CYF", "CYS",
    "EPF", "EPS", "ESF9", "ETS", "FAS", "MTF", "PBS", "PFF", "PFS", "PGF",
    "PGS", "PLS", "QH2F", "QHS1", "QHS2", "QNF", "QNS", "RSF", "RSS", "RVF",
    "SIF", "SIS", "SLF", "SLS", "TCF", "TCS",
]


def main():
    ap = argparse.ArgumentParser(description="SubductCR end-to-end workflow")
    ap.add_argument("--plan-only", action="store_true",
                    help="build and plan the DAG but do not submit")
    args = ap.parse_args()

    ctr             = make_containers()
    tc, T           = make_transformations(ctr)
    rc              = make_replicas(MG_SAMPLES)
    props           = make_properties()
    wf              = build_workflow(T, MG_SAMPLES)

    wf.add_transformation_catalog(tc)
    wf.add_replica_catalog(rc)
    props.write()

    backend = ("Shifter" if os.environ.get("SUBDUCTCR_USE_SHIFTER") == "1"
               else "Singularity" if os.environ.get("SUBDUCTCR_USE_SIF") == "1"
               else "Docker")
    print(f"SubductCR end-to-end workflow")
    print(f"  backend       : {backend}")
    print(f"  16S track     : KEBJ01 sequences -> ASVs (SILVA used directly)")
    print(f"  MG  track     : {len(MG_SAMPLES)} libraries -> enzymes")
    print(f"  total 16S+MG jobs wired.")

    # Where to run. On NERSC (Shifter) use the environment's "compute" site
    # (from ~/.pegasusrc -> nersc-perlmutter.yml) and skip our own site catalog
    # so the SFAPI/Slurm site is picked up. Otherwise plan for local execution.
    on_nersc = os.environ.get("SUBDUCTCR_USE_SHIFTER", "0") == "1"
    exec_site = os.environ.get("SUBDUCTCR_SITE", "compute" if on_nersc else "local")

    # Match the normal "pegasus-plan -e compute" behavior: just name the
    # execution site and let the environment handle everything else.
    plan_kwargs = dict(submit=not args.plan_only, dir=str(ROOT / "runs"))
    if on_nersc:
        plan_kwargs.update(sites=[exec_site])
    print(f"  execution site: {exec_site}")
    wf.plan(**plan_kwargs)


if __name__ == "__main__":
    main()