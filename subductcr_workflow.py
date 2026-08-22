#!/usr/bin/env python3
"""
subductcr_workflow.py
=====================================================================
Pegasus 5.x workflow generator that rebuilds the computational pipeline
of Fullerton et al. (2021), "Effect of tectonic processes on biosphere-
geosphere feedbacks across a convergent margin" (Nature Geoscience).

The wet-lab stages (sampling, DNA extraction, MiSeq/NextSeq sequencing)
are NOT part of this workflow -- they produce the raw read files that are
declared as inputs in the replica catalog. Everything from the reads
onward is expressed here as a DAG of jobs.

Two parallel tracks that fan out per sequencing library and then merge:

  16S amplicon track (teal):
    qc_16s[i]  ->  mothur  ->  filter_normalize  ->  asv_network  ->  clique_geochem
  Metagenome track (purple):
    trim[i]    ->  mifaser[i]  ->  gene_merge  ->  gene_network  ->  gene_geochem

  Shared endpoints:
    filter_normalize -> nmds_adonis
    (cell counts, geochem) -> carbon_flux
    everything -> make_report

Run:
    python3 subductcr_workflow.py            # generates + plans + submits
    python3 subductcr_workflow.py --no-run   # just write workflow.yml + catalogs

Requires: pegasus-wms.api >= 5.0  (pip install pegasus-wms.api)
=====================================================================
"""

import argparse
import os
from pathlib import Path

from Pegasus.api import (
    Arch,
    Container,
    File,
    Job,
    Namespace,
    OS,
    Operation,
    Properties,
    ReplicaCatalog,
    Site,
    SiteCatalog,
    Transformation,
    TransformationCatalog,
    Workflow,
    Directory,
    FileServer,
)

# ---------------------------------------------------------------------------
# 0. Project layout + sample sheet
# ---------------------------------------------------------------------------
BASE = Path(__file__).parent.resolve()
BIN = BASE / "bin"          # wrapper executables (see contract in each job)
INPUT = BASE / "input"      # raw reads, reference DBs, geochem table
WORK = BASE / "work"        # scratch / execution
OUTPUT = BASE / "output"    # staged-out final results
SIF_DIR = BASE / "containers" / "sif"   # where build_sif.sh writes the .sif files

# One entry per sequencing library. In the paper: 18 sites for 16S,
# with 10 also having metagenomes. Here samples carry flags for which
# track(s) they participate in.
SAMPLES = [
    # (name,   has_16s, has_metagenome)
    ("ES", True,  True),
    ("RS", True,  True),
    ("SM", True,  False),
    ("SR", True,  True),
    ("SI", True,  False),
    ("MT", True,  True),
    ("BQ", True,  False),
    ("VC", True,  True),
    ("BR", True,  True),
    ("CY", True,  False),
    ("SL", True,  True),
    ("QN", True,  True),
    ("TC", True,  False),
    ("RV", True,  True),
    ("ET", True,  False),
    ("QH", True,  True),
    ("EP", True,  False),
    ("HN", True,  False),
]
SAMPLES_16S = [s for s in SAMPLES if s[1]]
SAMPLES_MG = [s for s in SAMPLES if s[2]]


# ---------------------------------------------------------------------------
# 1. Pegasus properties
# ---------------------------------------------------------------------------
def build_properties() -> Properties:
    props = Properties()
    # Retry each failed job twice before giving up (per-job fault tolerance).
    props["dagman.retry"] = "2"
    # Integrity checking of staged files.
    props["pegasus.integrity.checking"] = "full"
    # Data staging: let HTCondor move files (no shared filesystem required).
    # Use "sharedfs" instead only if condorpool has a shared scratch mount;
    # then give the condorpool site a SHARED_SCRATCH dir + FileServer below.
    props["pegasus.data.configuration"] = "condorio"
    props.write()
    return props


# ---------------------------------------------------------------------------
# 2. Site catalog: where things run
# ---------------------------------------------------------------------------
def build_site_catalog() -> SiteCatalog:
    sc = SiteCatalog()

    # local: the submit host, used for planning + staging.
    local = Site("local", arch=Arch.X86_64, os_type=OS.LINUX)
    local_shared = Directory(Directory.SHARED_SCRATCH, path=str(WORK / "local-scratch"))
    local_shared.add_file_servers(FileServer("file://" + str(WORK / "local-scratch"), Operation.ALL))
    local_storage = Directory(Directory.LOCAL_STORAGE, path=str(OUTPUT))
    local_storage.add_file_servers(FileServer("file://" + str(OUTPUT), Operation.ALL))
    local.add_directories(local_shared, local_storage)
    sc.add_sites(local)

    # condorpool: an HTCondor cluster that actually runs the compute jobs.
    # With condorio (default in build_properties) no scratch file server is
    # needed here. If you switch to sharedfs, uncomment the SHARED_SCRATCH
    # block below and point it at a path shared across the pool.
    pool = Site("condorpool", arch=Arch.X86_64, os_type=OS.LINUX)
    # pool_scratch = Directory(Directory.SHARED_SCRATCH, path=str(WORK / "condorpool-scratch"))
    # pool_scratch.add_file_servers(FileServer("file://" + str(WORK / "condorpool-scratch"), Operation.ALL))
    # pool.add_directories(pool_scratch)
    pool.add_condor_profile(universe="vanilla")
    pool.add_pegasus_profile(style="condor")
    sc.add_sites(pool)

    sc.write()
    return sc


# ---------------------------------------------------------------------------
# 3. Containers: one per tool family so conflicting deps stay isolated
# ---------------------------------------------------------------------------
def build_containers():
    """Container definitions with a Docker <-> Singularity(.sif) toggle.

    Default: pull Docker images from Docker Hub (built by
    containers/build_and_push.sh).

    Set the environment variable SUBDUCTCR_USE_SIF=1 to use local .sif files
    instead (built by containers/build_sif.sh into containers/sif/). This is
    the right choice for HPC clusters that run Singularity/Apptainer and whose
    compute nodes cannot reach Docker Hub.
    """
    DOCKER_USER = "swarmourr"
    TAG = "1.0"
    USE_SIF = os.environ.get("SUBDUCTCR_USE_SIF", "0") == "1"

    # logical container name -> tool key (matches image + .sif filenames)
    specs = {
        "mothur_ctr": "mothur",
        "bio_ctr": "qc",       # trimmomatic + vsearch; used by qc_16s + trim_reads
        "mifaser_ctr": "mifaser",
        "r_ctr": "r",          # phyloseq, vegan, igraph, VSURF, missForest, ggplot2
    }

    def make(name, tool):
        if USE_SIF:
            return Container(
                name,
                Container.SINGULARITY,
                image=f"file://{SIF_DIR}/subductcr-{tool}.sif",
                image_site="local",
            )
        return Container(
            name,
            Container.DOCKER,
            image=f"docker://{DOCKER_USER}/subductcr-{tool}:{TAG}",
        )

    mothur_c = make("mothur_ctr", specs["mothur_ctr"])
    bio_c = make("bio_ctr", specs["bio_ctr"])
    mifaser_c = make("mifaser_ctr", specs["mifaser_ctr"])
    r_c = make("r_ctr", specs["r_ctr"])
    return mothur_c, bio_c, mifaser_c, r_c


# ---------------------------------------------------------------------------
# 4. Transformation catalog: the executables (wrapper scripts in bin/)
# ---------------------------------------------------------------------------
def build_transformation_catalog(mothur_c, bio_c, mifaser_c, r_c) -> TransformationCatalog:
    tc = TransformationCatalog()
    tc.add_containers(mothur_c, bio_c, mifaser_c, r_c)

    def T(name, container):
        t = Transformation(
            name,
            site="local",
            pfn=str(BIN / name),
            is_stageable=True,
            container=container,
        )
        return t

    # --- 16S track ---
    # bin/qc_16s   R1 R2 out.fasta   (QC, merge pairs, UCHIME chimera removal)
    qc_16s = T("qc_16s", bio_c)
    # bin/mothur_asv  <cleaned fastas...> silva.db  asv_table.tsv taxonomy.tsv
    mothur_asv = (
        T("mothur_asv", mothur_c)
        .add_profiles(Namespace.CONDOR, key="request_cpus", value="8")
        .add_profiles(Namespace.CONDOR, key="request_memory", value="32 GB")
        .add_profiles(Namespace.PEGASUS, key="runtime", value="21600")  # 6 h
    )
    # bin/filter_normalize  asv_table.tsv taxonomy.tsv geochem.csv  -> filtered.rds
    filter_normalize = T("filter_normalize", r_c).add_profiles(
        Namespace.CONDOR, key="request_memory", value="16 GB"
    )
    # bin/asv_network  filtered.rds  -> asv_cliques.rds edges.tsv
    asv_network = T("asv_network", r_c).add_profiles(
        Namespace.CONDOR, key="request_memory", value="16 GB"
    )
    # bin/clique_geochem  asv_cliques.rds geochem.csv -> asv_clique_env.tsv
    clique_geochem = T("clique_geochem", r_c)

    # --- Metagenome track ---
    # bin/trim_reads  R1 R2  out_R1.fq out_R2.fq
    trim_reads = T("trim_reads", bio_c).add_profiles(
        Namespace.CONDOR, key="request_cpus", value="4"
    )
    # bin/mifaser  R1 R2 gsplus.db  enzyme_abund.tsv
    mifaser = (
        T("mifaser", mifaser_c)
        .add_profiles(Namespace.CONDOR, key="request_cpus", value="8")
        .add_profiles(Namespace.CONDOR, key="request_memory", value="24 GB")
        .add_profiles(Namespace.PEGASUS, key="runtime", value="18000")  # 5 h
    )
    # bin/gene_merge  <enzyme_abund.tsv...>  gene_table.tsv   (merge + normalize)
    gene_merge = T("gene_merge", r_c)
    # bin/gene_network  gene_table.tsv  -> gene_cliques.rds
    gene_network = T("gene_network", r_c).add_profiles(
        Namespace.CONDOR, key="request_memory", value="16 GB"
    )
    # bin/gene_geochem  gene_cliques.rds geochem.csv -> gene_clique_env.tsv
    gene_geochem = T("gene_geochem", r_c)

    # --- Shared endpoints ---
    # bin/nmds_adonis  filtered.rds geochem.csv -> nmds.tsv adonis.tsv fig2.pdf
    nmds_adonis = T("nmds_adonis", r_c).add_profiles(
        Namespace.CONDOR, key="request_memory", value="16 GB"
    )
    # bin/carbon_flux  cell_counts.csv geochem.csv params.yml -> flux.tsv
    carbon_flux = T("carbon_flux", r_c)
    # bin/make_report  <all result files...>  report.html
    make_report = T("make_report", r_c)

    tc.add_transformations(
        qc_16s, mothur_asv, filter_normalize, asv_network, clique_geochem,
        trim_reads, mifaser, gene_merge, gene_network, gene_geochem,
        nmds_adonis, carbon_flux, make_report,
    )
    tc.write()
    return tc


# ---------------------------------------------------------------------------
# 5. Replica catalog: physical locations of all input files
# ---------------------------------------------------------------------------
def build_replica_catalog():
    rc = ReplicaCatalog()

    # Shared references.
    silva = File("silva_v132.db")
    gsplus = File("gsplus.db")
    geochem = File("geochem.csv")           # Supplementary Tables 1-3
    cell_counts = File("cell_counts.csv")   # flow-cytometry cell densities
    flux_params = File("flux_params.yml")   # t2, f_autotroph, C_cells, f_attached...

    rc.add_replica("local", silva, str(INPUT / "silva_v132.db"))
    rc.add_replica("local", gsplus, str(INPUT / "gsplus.db"))
    rc.add_replica("local", geochem, str(INPUT / "geochem.csv"))
    rc.add_replica("local", cell_counts, str(INPUT / "cell_counts.csv"))
    rc.add_replica("local", flux_params, str(INPUT / "flux_params.yml"))

    # Per-sample raw reads.
    reads = {}
    for name, has_16s, has_mg in SAMPLES:
        if has_16s:
            r1 = File(f"{name}_16S_R1.fastq.gz")
            r2 = File(f"{name}_16S_R2.fastq.gz")
            rc.add_replica("local", r1, str(INPUT / f"{name}_16S_R1.fastq.gz"))
            rc.add_replica("local", r2, str(INPUT / f"{name}_16S_R2.fastq.gz"))
            reads[(name, "16s")] = (r1, r2)
        if has_mg:
            m1 = File(f"{name}_MG_R1.fastq.gz")
            m2 = File(f"{name}_MG_R2.fastq.gz")
            rc.add_replica("local", m1, str(INPUT / f"{name}_MG_R1.fastq.gz"))
            rc.add_replica("local", m2, str(INPUT / f"{name}_MG_R2.fastq.gz"))
            reads[(name, "mg")] = (m1, m2)

    rc.write()
    refs = dict(silva=silva, gsplus=gsplus, geochem=geochem,
                cell_counts=cell_counts, flux_params=flux_params)
    return rc, refs, reads


# ---------------------------------------------------------------------------
# 6. Assemble the workflow (the DAG)
# ---------------------------------------------------------------------------
def build_workflow(refs, reads) -> Workflow:
    wf = Workflow("subductcr")

    silva = refs["silva"]
    gsplus = refs["gsplus"]
    geochem = refs["geochem"]

    # === 16S TRACK ============================================================
    # Fan-out: one qc_16s job per amplicon library.
    cleaned_fastas = []
    for name, _, _ in SAMPLES_16S:
        r1, r2 = reads[(name, "16s")]
        clean = File(f"{name}_16S_clean.fasta")
        j = (
            Job("qc_16s", _id=f"qc_{name}")
            .add_args(r1, r2, clean)
            .add_inputs(r1, r2)
            .add_outputs(clean, stage_out=False, register_replica=False)
        )
        wf.add_jobs(j)
        cleaned_fastas.append(clean)

    # Merge: mothur builds the ASV table + SILVA taxonomy from all libraries.
    asv_table = File("asv_table.tsv")
    taxonomy = File("taxonomy.tsv")
    mothur_job = (
        Job("mothur_asv", _id="mothur")
        .add_args(*cleaned_fastas, silva, asv_table, taxonomy)
        .add_inputs(*cleaned_fastas, silva)
        .add_outputs(asv_table, taxonomy, stage_out=True, register_replica=True)
    )
    wf.add_jobs(mothur_job)

    # phyloseq: remove low-prevalence ASVs, contaminants, chloroplast/mito;
    # drop hyperacidic outlier PL; normalize to relative abundance x median lib size.
    filtered = File("filtered.rds")
    filt_job = (
        Job("filter_normalize", _id="filter")
        .add_args(asv_table, taxonomy, geochem, filtered)
        .add_inputs(asv_table, taxonomy, geochem)
        .add_outputs(filtered, stage_out=True, register_replica=True)
    )
    wf.add_jobs(filt_job)

    # igraph: Spearman co-occurrence network (rho > 0.7) + Louvain cliques.
    asv_cliques = File("asv_cliques.rds")
    asv_edges = File("asv_edges.tsv")
    net_job = (
        Job("asv_network", _id="asv_net")
        .add_args(filtered, asv_cliques, asv_edges)
        .add_inputs(filtered)
        .add_outputs(asv_cliques, asv_edges, stage_out=True, register_replica=True)
    )
    wf.add_jobs(net_job)

    # VSURF random forest + Spearman/Pearson: clique abundance vs geochemistry.
    asv_clique_env = File("asv_clique_env.tsv")
    cg_job = (
        Job("clique_geochem", _id="asv_cg")
        .add_args(asv_cliques, geochem, asv_clique_env)
        .add_inputs(asv_cliques, geochem)
        .add_outputs(asv_clique_env, stage_out=True, register_replica=True)
    )
    wf.add_jobs(cg_job)

    # === METAGENOME TRACK ====================================================
    enzyme_tables = []
    for name, _, _ in SAMPLES_MG:
        m1, m2 = reads[(name, "mg")]
        # Fan-out: Trimmomatic per library.
        t1 = File(f"{name}_MG_R1.trim.fq.gz")
        t2 = File(f"{name}_MG_R2.trim.fq.gz")
        trim_job = (
            Job("trim_reads", _id=f"trim_{name}")
            .add_args(m1, m2, t1, t2)
            .add_inputs(m1, m2)
            .add_outputs(t1, t2, stage_out=False, register_replica=False)
        )
        wf.add_jobs(trim_job)

        # Fan-out: Mifaser annotation per library -> per-sample enzyme abundances.
        enz = File(f"{name}_enzymes.tsv")
        mif_job = (
            Job("mifaser", _id=f"mifaser_{name}")
            .add_args(t1, t2, gsplus, enz)
            .add_inputs(t1, t2, gsplus)
            .add_outputs(enz, stage_out=False, register_replica=False)
        )
        wf.add_jobs(mif_job)
        enzyme_tables.append(enz)

    # Merge: combine per-sample enzyme abundances, normalize to median lib size.
    gene_table = File("gene_table.tsv")
    gm_job = (
        Job("gene_merge", _id="gene_merge")
        .add_args(*enzyme_tables, gene_table)
        .add_inputs(*enzyme_tables)
        .add_outputs(gene_table, stage_out=True, register_replica=True)
    )
    wf.add_jobs(gm_job)

    # Gene co-occurrence cliques (Wood-Ljungdahl, rTCA, CBB gene-cliques).
    gene_cliques = File("gene_cliques.rds")
    gn_job = (
        Job("gene_network", _id="gene_net")
        .add_args(gene_table, gene_cliques)
        .add_inputs(gene_table)
        .add_outputs(gene_cliques, stage_out=True, register_replica=True)
    )
    wf.add_jobs(gn_job)

    # Gene-clique vs geochemistry (rTCA gene-clique B best correlates with DIC).
    gene_clique_env = File("gene_clique_env.tsv")
    gg_job = (
        Job("gene_geochem", _id="gene_cg")
        .add_args(gene_cliques, geochem, gene_clique_env)
        .add_inputs(gene_cliques, geochem)
        .add_outputs(gene_clique_env, stage_out=True, register_replica=True)
    )
    wf.add_jobs(gg_job)

    # === SHARED ENDPOINTS ====================================================
    # NMDS ordination + ADONIS PERMANOVA on the filtered community (Fig. 2).
    nmds = File("nmds.tsv")
    adonis = File("adonis.tsv")
    fig2 = File("fig2_clustering.pdf")
    nmds_job = (
        Job("nmds_adonis", _id="nmds")
        .add_args(filtered, geochem, nmds, adonis, fig2)
        .add_inputs(filtered, geochem)
        .add_outputs(nmds, adonis, fig2, stage_out=True, register_replica=True)
    )
    wf.add_jobs(nmds_job)

    # Carbon-flux calculation (Eqs. 1-4: residence time, biomass C, % of mantle input).
    flux = File("carbon_flux.tsv")
    flux_job = (
        Job("carbon_flux", _id="flux")
        .add_args(refs["cell_counts"], geochem, refs["flux_params"], flux)
        .add_inputs(refs["cell_counts"], geochem, refs["flux_params"])
        .add_outputs(flux, stage_out=True, register_replica=True)
    )
    wf.add_jobs(flux_job)

    # Final report: pull every result together (true convergence node).
    report = File("report.html")
    rep_job = (
        Job("make_report", _id="report")
        .add_args(asv_clique_env, gene_clique_env, nmds, adonis, fig2, flux, report)
        .add_inputs(asv_clique_env, gene_clique_env, nmds, adonis, fig2, flux)
        .add_outputs(report, stage_out=True, register_replica=True)
    )
    wf.add_jobs(rep_job)

    return wf


# ---------------------------------------------------------------------------
# 7. Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Build the SubductCR Pegasus workflow.")
    ap.add_argument("--no-run", action="store_true",
                    help="write workflow.yml + catalogs only; do not plan/submit")
    args = ap.parse_args()

    build_properties()
    build_site_catalog()
    mothur_c, bio_c, mifaser_c, r_c = build_containers()
    build_transformation_catalog(mothur_c, bio_c, mifaser_c, r_c)
    _, refs, reads = build_replica_catalog()

    wf = build_workflow(refs, reads)
    wf.write()  # emits workflow.yml (abstract DAG)

    print(f"16S libraries : {len(SAMPLES_16S)}")
    print(f"MG libraries  : {len(SAMPLES_MG)}")
    print(f"Total jobs    : {len(SAMPLES_16S) + 2*len(SAMPLES_MG) + 8}")

    if args.no_run:
        print("Wrote workflow.yml, properties, and catalogs. Skipping plan/run.")
        return

    # Plan the abstract workflow into an executable one and submit it.
    # To enable horizontal clustering, add clusters.size profiles to the
    # per-sample Transformations and pass cluster=["horizontal"] here.
    wf.plan(
        dir=str(WORK),
        sites=["condorpool"],
        output_sites=["local"],
        submit=True,
    ).wait()

    wf.statistics()


if __name__ == "__main__":
    main()
