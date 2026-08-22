#!/usr/bin/env python3
"""
reproduce_workflow.py
=====================================================================
Pegasus workflow that REPRODUCES Fullerton et al. (2021) directly from the
authors' published tables in reference_data/ -- no raw reads, no SILVA, no
mothur, no mi-faser. This mirrors the paper's Methods, which begin from the
count table, taxonomy, tree and environmental data (not from reads).

DAG (4 jobs):
    rep_16s          count + sample_table -> ASV cliques, clique-env, NMDS, ADONIS, Fig.2
    rep_metagenome   mifaser_dataset + ec_list_carbon + sample_table -> gene-cliques, gene-env
    rep_carbon_flux  sample_table + flux_params -> carbon-flux (Eqs 1-4)
    rep_report       everything -> report.html

Container backend (shared with subductcr_workflow.py):
    default = Docker Hub image;  SUBDUCTCR_USE_SIF=1 = local .sif.

Run:
    export SUBDUCTCR_USE_SIF=1          # on the cluster
    python3 reproduce_workflow.py       # plan + submit
    python3 reproduce_workflow.py --plan-only
    python3 reproduce_workflow.py --no-run
=====================================================================
"""

import argparse
import os
from pathlib import Path

from Pegasus.api import (
    Arch, Container, Directory, File, FileServer, Job, Operation, OS,
    Properties, Site, SiteCatalog, Transformation, TransformationCatalog,
    Workflow, ReplicaCatalog,
)

BASE = Path(__file__).parent.resolve()
BIN = BASE / "bin"
REF = BASE / "reference_data"
INPUT = BASE / "input"
WORK = BASE / "work"
OUTPUT = BASE / "output"
SIF_DIR = BASE / "containers" / "sif"


def build_properties() -> Properties:
    p = Properties()
    p["dagman.retry"] = "2"
    p["pegasus.integrity.checking"] = "full"
    p["pegasus.data.configuration"] = "condorio"
    p.write()
    return p


def build_site_catalog() -> SiteCatalog:
    sc = SiteCatalog()
    local = Site("local", arch=Arch.X86_64, os_type=OS.LINUX)
    scratch = Directory(Directory.SHARED_SCRATCH, path=str(WORK / "local-scratch"))
    scratch.add_file_servers(FileServer("file://" + str(WORK / "local-scratch"), Operation.ALL))
    storage = Directory(Directory.LOCAL_STORAGE, path=str(OUTPUT))
    storage.add_file_servers(FileServer("file://" + str(OUTPUT), Operation.ALL))
    local.add_directories(scratch, storage)
    sc.add_sites(local)

    pool = Site("condorpool", arch=Arch.X86_64, os_type=OS.LINUX)
    pool.add_condor_profile(universe="vanilla")
    pool.add_pegasus_profile(style="condor")
    sc.add_sites(pool)
    sc.write()
    return sc


def r_container():
    """The R container only -- all reproduce jobs are R."""
    user = "swarmourr"; tag = "1.0"
    if os.environ.get("SUBDUCTCR_USE_SIF", "0") == "1":
        return Container("r_ctr", Container.SINGULARITY,
                         image=f"file://{SIF_DIR}/subductcr-r.sif", image_site="local")
    return Container("r_ctr", Container.DOCKER,
                     image=f"docker://{user}/subductcr-r:{tag}")


def build_tc(r_c) -> TransformationCatalog:
    tc = TransformationCatalog()
    tc.add_containers(r_c)

    rep_16s = Transformation("rep_16s", site="local", pfn=str(BIN / "rep_16s"),
                             is_stageable=True, container=r_c)
    rep_mg = Transformation("rep_metagenome", site="local", pfn=str(BIN / "rep_metagenome"),
                            is_stageable=True, container=r_c)
    rep_flux = Transformation("rep_carbon_flux", site="local", pfn=str(BIN / "rep_carbon_flux"),
                              is_stageable=True, container=r_c)
    make_report = Transformation("make_report", site="local", pfn=str(BIN / "make_report"),
                                 is_stageable=True, container=r_c)
    tc.add_transformations(rep_16s, rep_mg, rep_flux, make_report)
    tc.write()
    return tc


def build_rc():
    rc = ReplicaCatalog()
    files = {
        "count":    (File("bac_normalized_count.csv"), REF / "16S_rRNA_data" / "bac_normalized_count.csv"),
        "sample":   (File("bac_sample_table.csv"),     REF / "16S_rRNA_data" / "bac_sample_table.csv"),
        "mifaser":  (File("mifaser_dataset.csv"),      REF / "mi-faser_metagenomes" / "mifaser_dataset.csv"),
        "ec":       (File("ec_list_carbon.csv"),       REF / "mi-faser_metagenomes" / "ec_list_carbon.csv"),
        "params":   (File("flux_params.yml"),          INPUT / "flux_params.yml"),
    }
    for _, (f, path) in files.items():
        rc.add_replica("local", f, str(path))
    rc.write()
    return {k: v[0] for k, v in files.items()}


def build_workflow(F) -> Workflow:
    wf = Workflow("subductcr-reproduce")

    # --- 16S community analysis (Fig. 2 + Fig. 3) ---
    cliques = File("asv_cliques.rds"); clique_env = File("asv_clique_env.tsv")
    nmds = File("nmds.tsv"); adonis = File("adonis.tsv"); fig2 = File("fig2_nmds.pdf")
    j16 = (Job("rep_16s", _id="rep_16s")
           .add_args(F["count"], F["sample"], cliques, clique_env, nmds, adonis, fig2)
           .add_inputs(F["count"], F["sample"])
           .add_outputs(cliques, clique_env, nmds, adonis, fig2, stage_out=True, register_replica=True))
    wf.add_jobs(j16)

    # --- metagenome carbon-fixation gene cliques (Fig. 4) ---
    gene_cliques = File("gene_cliques.rds"); gene_env = File("gene_clique_env.tsv")
    jmg = (Job("rep_metagenome", _id="rep_metagenome")
           .add_args(F["mifaser"], F["ec"], F["sample"], gene_cliques, gene_env)
           .add_inputs(F["mifaser"], F["ec"], F["sample"])
           .add_outputs(gene_cliques, gene_env, stage_out=True, register_replica=True))
    wf.add_jobs(jmg)

    # --- carbon flux (Eqs 1-4) ---
    flux = File("carbon_flux.tsv")
    jflux = (Job("rep_carbon_flux", _id="rep_carbon_flux")
             .add_args(F["sample"], F["params"], flux)
             .add_inputs(F["sample"], F["params"])
             .add_outputs(flux, stage_out=True, register_replica=True))
    wf.add_jobs(jflux)

    # --- report (convergence) ---
    report = File("report.html")
    jrep = (Job("make_report", _id="rep_report")
            .add_args(clique_env, gene_env, nmds, adonis, fig2, flux, report)
            .add_inputs(clique_env, gene_env, nmds, adonis, fig2, flux)
            .add_outputs(report, stage_out=True, register_replica=True))
    wf.add_jobs(jrep)
    return wf


def main():
    ap = argparse.ArgumentParser(description="Reproduce Fullerton et al. from the authors' tables.")
    ap.add_argument("--no-run", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    args = ap.parse_args()

    build_properties(); build_site_catalog()
    r_c = r_container(); build_tc(r_c)
    F = build_rc()
    wf = build_workflow(F)
    wf.write()
    print("Reproduce workflow: 4 jobs (rep_16s, rep_metagenome, rep_carbon_flux, rep_report)")
    print("Backend:", "SIF" if os.environ.get("SUBDUCTCR_USE_SIF")=="1" else "Docker")

    if args.no_run:
        print("Wrote workflow.yml + catalogs. Skipping plan/run."); return
    submit = not args.plan_only
    plan = wf.plan(dir=str(WORK), sites=["condorpool"], output_sites=["local"], submit=submit)
    if args.plan_only:
        print("Planned (not submitted). Submit with: pegasus-run <run-dir>"); return
    plan.wait(); wf.statistics()


if __name__ == "__main__":
    main()
