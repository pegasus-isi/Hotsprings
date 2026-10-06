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
    python3 workflow/end_to_end.py \
        --reuse-from /pscratch/sd/h/hsafri/wf-scratch/hsafri/pegasus/\
subductcr-end-to-end/run0032
        # reuse gene_table.tsv, regenerate gene_cliques.rds, gene geochemistry,
        # and carbon flux; omit trim/mIFASER/gene_merge; rerun all 16S jobs
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
            # Keep the full namespace (swarmourr/...). A two-slash shifter://
            # URL makes Pegasus treat "swarmourr" as the host and drop it, so
            # use three slashes (empty host) by default. Override with
            # SUBDUCTCR_SHIFTER_URL if a different form is needed:
            #   "3slash" -> shifter:///img   (default)
            #   "plain"  -> img
            #   "2slash" -> shifter://img
            fmt = os.environ.get("SUBDUCTCR_SHIFTER_URL", "3slash")
            if   fmt == "plain":  img = image
            elif fmt == "2slash": img = f"shifter://{image}"
            else:                 img = f"shifter:///{image}"
            return Container(name, Container.SHIFTER,
                             image=img, bypass_staging=True)
        if sif:
            path = ROOT / "containers" / "sif" / f"{name}.sif"
            return Container(name, Container.SINGULARITY,
                             image=f"file://{path}", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")

    tag = os.environ.get("SUBDUCTCR_TAG", "1.0")
    return {
        "r":       container("subductcr-r",       f"swarmourr/subductcr-r:{tag}"),
        "mothur":  container("subductcr-mothur",  f"swarmourr/subductcr-mothur:{tag}"),
        "mifaser": container("subductcr-mifaser", f"swarmourr/subductcr-mifaser:{tag}"),
    }


# --------------------------------------------------------------------------
# transformations  (bin/ scripts -> Pegasus jobs)
# --------------------------------------------------------------------------
def make_transformations(ctr):
    """One Transformation per wrapper in bin/. mem/cpus kept modest & explicit."""
    def T(name, container, mem_gb=16, cpus=1, runtime=43200, queue="shared"):
        t = Transformation(name, site="local",
                           pfn=str(BIN / name), is_stageable=True,
                           container=container)
        t.add_profiles(Namespace.PEGASUS, key="memory",  value=str(mem_gb * 1024))
        t.add_profiles(Namespace.PEGASUS, key="cores",   value=str(cpus))
        # runtime (seconds) so kickstart / Slurm don't kill long download+
        # process jobs. Default 4 h; the Slurm walltime is set from this too.
        t.add_profiles(Namespace.PEGASUS, key="runtime",      value=str(runtime))
        t.add_profiles(Namespace.PEGASUS, key="maxwalltime",  value=str(runtime // 60))  # minutes
        t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value="-C cpu")
        t.add_profiles(Namespace.PEGASUS, key="queue", value=queue)
        return t

    tc = TransformationCatalog()
    tents = {
        # 16S track
        "mothur_asv":       T("mothur_asv",       ctr["mothur"],  mem_gb=128, cpus=8, runtime=86400, queue="regular"),
        "filter_normalize": T("filter_normalize", ctr["r"]),
        "asv_network":      T("asv_network",      ctr["r"]),
        "nmds_adonis":      T("nmds_adonis",      ctr["r"]),
        "clique_geochem":   T("clique_geochem",   ctr["r"]),
        # metagenome track
        "trim_reads":       T("trim_reads",        ctr["mothur"],  mem_gb=16,  cpus=8, runtime=43200, queue="shared"),
        "mifaser":          T("mifaser",           ctr["mifaser"], mem_gb=128, cpus=8, runtime=86400, queue="regular"),
        "gene_merge":       T("gene_merge",       ctr["r"]),
        "gene_network":     T("gene_network",     ctr["r"]),
        "gene_geochem":     T("gene_geochem",     ctr["r"]),
        "carbon_flux":      T("carbon_flux",      ctr["r"]),
        # shared
        "make_report":      T("make_report",      ctr["r"]),
    }
    tc.add_transformations(*tents.values())

    # pegasus::transfer with an sshproxy validity-check PRE script, so the NERSC
    # SSH cert is confirmed valid before any transfer job runs (prevents mid-run
    # auth failures during staging to/from Perlmutter). The check script lives
    # on the ACCESS/Pegasus submit host. Disable with SUBDUCTCR_SSHPROXY_CHECK=0.
    if os.environ.get("SUBDUCTCR_SSHPROXY_CHECK", "1") == "1":
        xfer = Transformation("transfer", namespace="pegasus",
                              site="local", pfn="/usr/bin/pegasus-transfer",
                              is_stageable=False)
        sshcheck = os.environ.get("SUBDUCTCR_SSHPROXY_SCRIPT",
                                  "/tmp/sshproxy-validity-check")
        sshcert  = os.environ.get("SUBDUCTCR_SSHPROXY_CERT",
                                  os.path.expanduser("~/.ssh/nersc-cert.pub"))
        xfer.add_profiles(Namespace.DAGMAN, key="PRE",           value=sshcheck)
        xfer.add_profiles(Namespace.DAGMAN, key="PRE.ARGUMENTS", value=sshcert)
        tc.add_transformations(xfer)

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
def make_replicas(mg_samples, previous_run=None):
    rc = ReplicaCatalog()

    def add(lfn, path, site="local"):
        rc.add_replica(site, lfn, str(path))

    # 16S inputs
    add("kebj01_16s.fasta",   S16 / "kebj01_16s.fasta")
    add("silva_v132.db",      REF / "silva_v132.db")
    add("silva_v132.tax",     REF / "silva_v132.tax")
    # Environmental data are always needed by the rerun 16S analyses.
    add("geochem.csv", REF / "geochem.csv")

    if previous_run is not None:
        # Reuse the merged gene table already on NERSC. The new workflow will
        # regenerate the gene network, cliques, gene-geochemistry, and carbon.
        # Use an explicit remote URL because planning occurs on ACCESS, where
        # /pscratch is not mounted. A bare /pscratch path would be interpreted
        # by pegasus-transfer as a local ACCESS path and fail with "Expected
        # local file does not exist".
        nersc_user = os.environ.get("RESOURCE_USERNAME", "hsafri")
        nersc_dtn = os.environ.get("SUBDUCTCR_NERSC_DTN", "dtn01.nersc.gov")
        gene_table_path = previous_run / "gene_table.tsv"
        gene_table_url = f"scp://{nersc_user}@{nersc_dtn}/{gene_table_path}"
        add("gene_table.tsv", gene_table_url, site="compute")
        add("cell_counts.csv", REF / "cell_counts.csv")
        add("flux_params.yml", CONFIG / "flux_params.yml")
    else:
        # Full-run mode: register inputs needed to execute the MG/gene/carbon
        # branch. If requested, use already-trimmed reads.
        skip_trim = os.environ.get("SUBDUCTCR_SKIP_TRIM", "0") == "1"
        if skip_trim:
            for s in mg_samples:
                add(f"{s}_trim_R1.fastq.gz",
                    DATA / "trimmed" / f"{s}_trim_R1.fastq.gz")
                add(f"{s}_trim_R2.fastq.gz",
                    DATA / "trimmed" / f"{s}_trim_R2.fastq.gz")
        else:
            for s in mg_samples:
                add(f"{s}_R1.fastq.gz", MG / f"{s}_R1.fastq.gz")
                add(f"{s}_R2.fastq.gz", MG / f"{s}_R2.fastq.gz")
        add("ec_carbon.csv",   REF / "ec_carbon.csv")
        add("cell_counts.csv", REF / "cell_counts.csv")
        add("flux_params.yml", CONFIG / "flux_params.yml")
    return rc




# --------------------------------------------------------------------------
# ENA read map  (the proven sample -> fastq URL mapping, read once here)
# --------------------------------------------------------------------------
def load_ena_map():
    """Read config/ena_MG.tsv into {sample: (r1_url, r2_url)}.
    Accepts either 'sample<TAB>...<TAB>fastq_ftp(R1;R2)' or
    'sample<TAB>r1_url<TAB>r2_url'. Returns {} if the file is absent."""
    import csv, re
    # look for the mapping in the usual places (data/reference or config)
    candidates = [REF / "ena_map.tsv", REF / "ena_MG.tsv",
                  CONFIG / "ena_map.tsv", CONFIG / "ena_MG.tsv"]
    path = next((p for p in candidates if p.exists()), candidates[0])
    m = {}
    if not path.exists():
        return m
    with open(path) as fh:
        for row in csv.reader(fh, delimiter="\t"):
            if not row or row[0].lower() in ("sample", "run_accession"):
                continue
            sample = row[0].split("_")[0]
            # gather any fastq .gz urls in the row
            urls = []
            for cell in row:
                for u in re.split(r"[;,]", cell):
                    if ".fastq.gz" in u or "fastq" in u and ".gz" in u:
                        urls.append(u.strip())
            if len(urls) >= 2:
                r1 = next((u for u in urls if re.search(r"_1\.|_R1|R1", u)), urls[0])
                r2 = next((u for u in urls if re.search(r"_2\.|_R2|R2", u)), urls[1])
                r1 = r1 if r1.startswith("http") else "https://" + r1
                r2 = r2 if r2.startswith("http") else "https://" + r2
                m[sample] = (r1, r2)
    return m

# --------------------------------------------------------------------------
# the workflow  (inputs -> jobs -> outputs)
# --------------------------------------------------------------------------
def build_workflow(T, mg_samples, previous_run=None):
    wf = Workflow("subductcr-end-to-end")
    ena = load_ena_map()   # {sample: (r1_url, r2_url)} from the proven mapping

    # ---- shared input files ----
    geochem = File("geochem.csv")

    # ======================================================================
    # 16S track :  KEBJ01 sequences -> ASVs -> community structure
    # ======================================================================
    asv_table = File("asv_table.tsv"); taxonomy = File("taxonomy.tsv")

    # SILVA is used DIRECTLY from mothur (no separate trimming job).
    kebj = File("kebj01_16s.fasta")
    silva_db = File("silva_v132.db"); silva_tax = File("silva_v132.tax")
    j_asv = (Job(T["mothur_asv"], _id="mothur_asv")
             .add_args(kebj, silva_db, silva_tax, asv_table, taxonomy)
             .add_inputs(kebj, silva_db, silva_tax)
             .add_outputs(asv_table, taxonomy, stage_out=True, register_replica=True))
    # Always rerun. The old ASV table treated every input read as a different
    # ASV, so no ASV could occur in more than one sample.

    filtered = File("filtered.rds")
    j_filt = (Job(T["filter_normalize"], _id="filter_normalize")
              .add_args(asv_table, taxonomy, filtered)
              .add_inputs(asv_table, taxonomy)
              .add_outputs(filtered, stage_out=True, register_replica=True))
    # Always rerun because filtered.rds depends on the corrected ASV table.

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
    # nmds_adonis is intentionally not marked reusable because the corrected
    # mothur/count-table output changes filtered.rds and every ASV analysis.

    asv_env = File("asv_clique_env.tsv")
    j_cg = (Job(T["clique_geochem"], _id="clique_geochem")
            .add_args(asv_cliques, filtered, geochem, asv_env)
            .add_inputs(asv_cliques, filtered, geochem)
            .add_outputs(asv_env, stage_out=True, register_replica=True))

    # ======================================================================
    # metagenome/gene/carbon track
    # ======================================================================
    other_branch_jobs = []

    if previous_run is not None:
        # Reuse only the merged gene table. Regenerate the gene network,
        # cliques, gene-geochemistry, and carbon products in this workflow.
        gene_table = File("gene_table.tsv")
        gene_cliques = File("gene_cliques.rds")
        j_gnet = (Job(T["gene_network"], _id="gene_network")
                  .add_args(gene_table, gene_cliques)
                  .add_inputs(gene_table)
                  .add_outputs(gene_cliques, stage_out=True,
                               register_replica=True))

        gene_env = File("gene_clique_env.tsv")
        j_gg = (Job(T["gene_geochem"], _id="gene_geochem")
                .add_args(gene_cliques, geochem, gene_env)
                .add_inputs(gene_cliques, geochem)
                .add_outputs(gene_env, stage_out=True,
                             register_replica=True))

        cells = File("cell_counts.csv")
        flux_par = File("flux_params.yml")
        carbon = File("carbon_flux.tsv")
        j_flux = (Job(T["carbon_flux"], _id="carbon_flux")
                  .add_args(geochem, cells, flux_par, carbon)
                  .add_inputs(geochem, cells, flux_par)
                  .add_outputs(carbon, stage_out=True,
                               register_replica=True))

        other_branch_jobs.extend([j_gnet, j_gg, j_flux])
    else:
        cells = File("cell_counts.csv")
        flux_par = File("flux_params.yml")
        ec_carbon = File("ec_carbon.csv")

        enzyme_files = []
        for s in mg_samples:
            t1 = File(f"{s}_trim_R1.fastq.gz")
            t2 = File(f"{s}_trim_R2.fastq.gz")

            if os.environ.get("SUBDUCTCR_SKIP_TRIM", "0") != "1":
                r1 = File(f"{s}_R1.fastq.gz")
                r2 = File(f"{s}_R2.fastq.gz")
                j_trim = (Job(T["trim_reads"], _id=f"trim_{s}")
                          .add_args(r1, r2, t1, t2)
                          .add_inputs(r1, r2)
                          .add_outputs(t1, t2, stage_out=False,
                                       register_replica=False))
                other_branch_jobs.append(j_trim)

            enz = File(f"{s}_enzymes.tsv")
            j_mifaser = (Job(T["mifaser"], _id=f"mifaser_{s}")
                         .add_args(t1, t2, enz)
                         .add_inputs(t1, t2)
                         .add_outputs(enz, stage_out=True,
                                      register_replica=True))
            other_branch_jobs.append(j_mifaser)
            enzyme_files.append(enz)

        gene_table = File("gene_table.tsv")
        j_gmerge = (Job(T["gene_merge"], _id="gene_merge")
                    .add_args(ec_carbon, gene_table, *enzyme_files)
                    .add_inputs(ec_carbon, *enzyme_files)
                    .add_outputs(gene_table, stage_out=True,
                                 register_replica=True))

        gene_cliques = File("gene_cliques.rds")
        j_gnet = (Job(T["gene_network"], _id="gene_network")
                  .add_args(gene_table, gene_cliques)
                  .add_inputs(gene_table)
                  .add_outputs(gene_cliques, stage_out=True,
                               register_replica=True))

        gene_env = File("gene_clique_env.tsv")
        j_gg = (Job(T["gene_geochem"], _id="gene_geochem")
                .add_args(gene_cliques, geochem, gene_env)
                .add_inputs(gene_cliques, geochem)
                .add_outputs(gene_env, stage_out=True,
                             register_replica=True))

        carbon = File("carbon_flux.tsv")
        j_flux = (Job(T["carbon_flux"], _id="carbon_flux")
                  .add_args(geochem, cells, flux_par, carbon)
                  .add_inputs(geochem, cells, flux_par)
                  .add_outputs(carbon, stage_out=True,
                               register_replica=True))

        other_branch_jobs.extend([j_gmerge, j_gnet, j_gg, j_flux])

    # ======================================================================
    # report :  bring both tracks together
    # ======================================================================
    report = File("report.html")
    j_rep = (Job(T["make_report"], _id="make_report")
             .add_args(asv_env, gene_env, nmds, adonis, carbon, report)
             .add_inputs(asv_env, gene_env, nmds, adonis, carbon)
             .add_outputs(report, stage_out=True, register_replica=True))

    wf.add_jobs(j_asv, j_filt, j_net, j_nmds, j_cg, j_rep,
                *other_branch_jobs)
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
    p["pegasus.integrity.checking"] = "none"   # so wrapper edits don't fail checksum
    # run many jobs at once (default clustering can serialize to ~2)
    p["dagman.maxjobs"] = os.environ.get("SUBDUCTCR_MAXJOBS", "20")
    p["dagman.maxidle"] = "40"
    if os.environ.get("SUBDUCTCR_USE_SHIFTER", "0") != "1":
        # only for local/Docker runs
        p["pegasus.data.configuration"] = "condorio"
    return p


# --------------------------------------------------------------------------
# sample list  (34 metagenome libraries retrievable from ENA; QHS1 excluded)
# --------------------------------------------------------------------------
MG_SAMPLES = [
    "ARS", "BQF", "BQS", "BR1F", "BRF2", "BRS1", "BRS2", "CYF", "CYS",
    "EPF", "EPS", "ESF9", "ETS", "FAS", "MTF", "PBS", "PFF", "PFS", "PGF",
    "PGS", "PLS", "QH2F", "QHS2", "QNF", "QNS", "RSF", "RSS", "RVF",
    "SIF", "SIS", "SLF", "SLS", "TCF", "TCS",
]


# --------------------------------------------------------------------------
# default environment (only set if not already exported by the user)
# --------------------------------------------------------------------------
_DEFAULTS = {
    "SUBDUCTCR_USE_SHIFTER": "1",       # run on NERSC Perlmutter (Shifter)
    "SUBDUCTCR_TAG":         "latest",  # container image tag
    "RESOURCE_PROJECT":      "m4144",   # NERSC allocation
    "RESOURCE_USERNAME":     "hsafri",  # NERSC username
    "RESOURCE_SCRATCH_DIR":  os.environ.get("PSCRATCH", "/pscratch/sd/h/hsafri"),  # Perlmutter scratch
    "SSH_PRIVATE_KEY":       os.path.expanduser("~/.ssh/id_rsa"),  # for scp file transfers
}
for _k, _v in _DEFAULTS.items():
    os.environ.setdefault(_k, _v)


def main():
    ap = argparse.ArgumentParser(description="SubductCR end-to-end workflow")
    ap.add_argument("--plan-only", action="store_true",
                    help="build and plan the DAG but do not submit")
    ap.add_argument(
        "--reuse-from", "--reuse-asv-from",
        dest="reuse_from",
        type=Path,
        metavar="OLD_OUTPUT_DIR",
        help=("reuse gene_table.tsv from a previous NERSC /pscratch output "
              "directory; rerun gene_network, gene_geochem, and carbon_flux "
              "while omitting trim, mIFASER, and gene_merge"),
    )
    args = ap.parse_args()

    reuse_dir = None
    if args.reuse_from is not None:
        # This path belongs to the remote NERSC compute site and normally is
        # not mounted on the ACCESS submit host. Do not call exists(),
        # is_dir(), or resolve() here. Pegasus will validate/stage the
        # compute-site replicas when the workflow runs.
        reuse_dir = args.reuse_from.expanduser()
        if not reuse_dir.is_absolute():
            ap.error("--reuse-from must be the absolute NERSC output path "
                     "under /pscratch; do not use '.' or the ACCESS submit "
                     "directory")

    ctr             = make_containers()
    tc, T           = make_transformations(ctr)
    rc              = make_replicas(MG_SAMPLES, previous_run=reuse_dir)
    props           = make_properties()
    wf              = build_workflow(T, MG_SAMPLES, previous_run=reuse_dir)

    wf.add_transformation_catalog(tc)
    wf.add_replica_catalog(rc)
    props.write()

    backend = ("Shifter" if os.environ.get("SUBDUCTCR_USE_SHIFTER") == "1"
               else "Singularity" if os.environ.get("SUBDUCTCR_USE_SIF") == "1"
               else "Docker")
    print(f"SubductCR end-to-end workflow")
    print(f"  backend       : {backend}")
    print(f"  16S track     : KEBJ01 sequences -> ASVs (SILVA used directly)")
    if reuse_dir is None:
        print(f"  MG  track     : {len(MG_SAMPLES)} libraries -> enzymes")
        print("  mode          : full 16S + MG/gene/carbon workflow")
    else:
        print("  MG  track     : expensive preprocessing omitted")
        print("  old input     : gene_table.tsv")
        print("  regenerated   : gene_cliques.rds, gene_clique_env.tsv, "
              "carbon_flux.tsv")

    # Where to run. On NERSC (Shifter) use the environment's "compute" site
    # (from ~/.pegasusrc -> nersc-perlmutter.yml) and skip our own site catalog
    # so the SFAPI/Slurm site is picked up. Otherwise plan for local execution.
    on_nersc = os.environ.get("SUBDUCTCR_USE_SHIFTER", "0") == "1"
    exec_site = os.environ.get("SUBDUCTCR_SITE", "compute" if on_nersc else "local")

    # Match the normal "pegasus-plan -e compute" behavior: name the execution
    # site, and stage outputs back to "local" so results land in our folder.
    plan_kwargs = dict(submit=not args.plan_only, dir=str(ROOT / "runs"))
    if on_nersc:
        plan_kwargs.update(sites=[exec_site], output_sites=["local"])
    print(f"  execution site: {exec_site}")
    if reuse_dir is not None:
        print(f"  output source : compute:{reuse_dir}")
        print("  excluded jobs : trim_reads, mifaser, gene_merge")
        print("  forced rerun  : mothur_asv, filter_normalize, asv_network, "
              "nmds_adonis, clique_geochem, gene_network, gene_geochem, "
              "carbon_flux, make_report")
    wf.plan(**plan_kwargs)


if __name__ == "__main__":
    main()
