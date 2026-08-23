#!/usr/bin/env python3
#
# SubductCR reproduce workflow -- written in the Pegasus class-based generator
# style (cf. pegasus-isi/federated-learning-example/workflow_generator_sub.py).
#
# Reproduces Fullerton et al. (2021) from the authors' published tables:
#   rep_16s          -> ASV cliques, NMDS, ADONIS (Figs 2, 3)
#   rep_metagenome   -> carbon-fixation gene-cliques (Fig 4)
#   rep_carbon_flux  -> Eqs 1-4
#   make_report      -> report.html
#
# Backends:  SUBDUCTCR_USE_SIF=1 -> local .sif ;  else Docker Hub image.
#            SUBDUCTCR_BYPASS=1  -> bypass_staging on the container.
#
# Usage:
#   python3 reproduce_workflow.py                 # plan + submit (condorpool)
#   python3 reproduce_workflow.py -e local        # run on local site
#   python3 reproduce_workflow.py --plan-only
#   python3 reproduce_workflow.py --no-run

import os
from pathlib import Path
from argparse import ArgumentParser

from Pegasus.api import *


class SubductCRReproduceWorkflow():
    wf = None
    sc = None
    tc = None
    rc = None
    props = None

    dagfile = None
    wf_dir = None
    shared_scratch_dir = None
    local_storage_dir = None
    wf_name = "subductcr-reproduce"

    # --- Init -----------------------------------------------------------------
    def __init__(self, dagfile="workflow.yml"):
        self.dagfile = dagfile
        self.wf_dir = str(Path(__file__).parent.resolve())
        self.ref_dir = os.path.join(self.wf_dir, "reference_data")
        self.input_dir = os.path.join(self.wf_dir, "input")
        self.shared_scratch_dir = os.path.join(self.wf_dir, "work", "scratch")
        self.local_storage_dir = os.path.join(self.wf_dir, "output")
        self.use_sif = os.environ.get("SUBDUCTCR_USE_SIF", "0") == "1"
        self.bypass = os.environ.get("SUBDUCTCR_BYPASS", "0") == "1"
        return

    # --- Write files ----------------------------------------------------------
    def write(self, name):
        if self.sc is not None:
            self.sc.write()
        if self.props is not None:
            self.props.write()
        if self.rc is not None:
            self.rc.write()
        if self.tc is not None:
            self.tc.write()
        self.wf.write(name)
        return

    # --- Configuration (Pegasus Properties) -----------------------------------
    def create_pegasus_properties(self):
        self.props = Properties()
        self.props["dagman.retry"] = "5"
        self.props["pegasus.integrity.checking"] = "full"
        self.props["pegasus.data.configuration"] = "condorio"
        self.props["condor.periodic_release"] = "(NumJobStarts < 6) && (HoldReasonCode =!= 1)"
        self.props["condor.periodic_remove"] = "NumJobStarts > 6"
        return

    # --- Site Catalog ---------------------------------------------------------
    def create_sites_catalog(self, exec_site_name="condorpool"):
        self.sc = SiteCatalog()

        local = (Site("local")
                    .add_directories(
                        Directory(Directory.SHARED_SCRATCH, self.shared_scratch_dir)
                            .add_file_servers(FileServer("file://" + self.shared_scratch_dir, Operation.ALL)),
                        Directory(Directory.LOCAL_STORAGE, self.local_storage_dir)
                            .add_file_servers(FileServer("file://" + self.local_storage_dir, Operation.ALL))
                    )
                )

        exec_site = (Site(exec_site_name)
                        .add_condor_profile(universe="vanilla")
                        .add_pegasus_profile(style="condor"))

        self.sc.add_sites(local, exec_site)
        return

    # --- Transformation Catalog (executables + container) ---------------------
    def create_transformation_catalog(self, exec_site_name="condorpool"):
        self.tc = TransformationCatalog()

        if self.use_sif:
            r_ctr = Container("r_ctr",
                container_type=Container.SINGULARITY,
                image="file://" + os.path.join(self.wf_dir, "containers/sif/subductcr-r.sif"),
                image_site="local",
                bypass_staging=self.bypass)
        else:
            r_ctr = Container("r_ctr",
                container_type=Container.DOCKER,
                image="docker://swarmourr/subductcr-r:1.0",
                bypass_staging=self.bypass)

        # Work around "Failed to set mount propagation: Permission denied" on
        # execute nodes that forbid Apptainer's underlay/overlay mount setup.
        # These are exported into the job environment so Apptainer avoids the
        # mount step the node denies.
        for k, v in [
            ("APPTAINER_DISABLE_UNDERLAY", "1"),
            ("SINGULARITY_DISABLE_UNDERLAY", "1"),
            ("APPTAINER_DISABLE_OVERLAY", "1"),
            ("SINGULARITY_DISABLE_OVERLAY", "1"),
        ]:
            r_ctr.add_env(key=k, value=v)

        def b(n):
            return os.path.join(self.wf_dir, "bin", n)

        rep_16s = (Transformation("rep_16s", site=exec_site_name, pfn=b("rep_16s"),
                                  is_stageable=True, container=r_ctr)
                   .add_profiles(Namespace.PEGASUS, key="memory", value="16384")
                   .add_profiles(Namespace.PEGASUS, key="cores", value="2")
                   .add_profiles(Namespace.PEGASUS, key="diskspace", value="8192"))
        rep_metagenome = (Transformation("rep_metagenome", site=exec_site_name, pfn=b("rep_metagenome"),
                                         is_stageable=True, container=r_ctr)
                          .add_profiles(Namespace.PEGASUS, key="memory", value="8192"))
        rep_carbon_flux = (Transformation("rep_carbon_flux", site=exec_site_name, pfn=b("rep_carbon_flux"),
                                          is_stageable=True, container=r_ctr)
                           .add_profiles(Namespace.PEGASUS, key="memory", value="4096"))
        make_report = (Transformation("make_report", site=exec_site_name, pfn=b("make_report"),
                                      is_stageable=True, container=r_ctr)
                       .add_profiles(Namespace.PEGASUS, key="memory", value="4096"))

        self.tc.add_containers(r_ctr)
        self.tc.add_transformations(rep_16s, rep_metagenome, rep_carbon_flux, make_report)
        return

    # --- Replica Catalog ------------------------------------------------------
    def create_replica_catalog(self):
        self.rc = ReplicaCatalog()
        R = self.ref_dir
        self.rc.add_replica("local", "bac_normalized_count.csv",
                            os.path.join(R, "16S_rRNA_data", "bac_normalized_count.csv"))
        self.rc.add_replica("local", "bac_sample_table.csv",
                            os.path.join(R, "16S_rRNA_data", "bac_sample_table.csv"))
        self.rc.add_replica("local", "mifaser_dataset.csv",
                            os.path.join(R, "mi-faser_metagenomes", "mifaser_dataset.csv"))
        self.rc.add_replica("local", "ec_list_carbon.csv",
                            os.path.join(R, "mi-faser_metagenomes", "ec_list_carbon.csv"))
        self.rc.add_replica("local", "flux_params.yml",
                            os.path.join(self.input_dir, "flux_params.yml"))
        return

    # --- Create Workflow ------------------------------------------------------
    def create_workflow(self):
        self.wf = Workflow(self.wf_name, infer_dependencies=True)

        count = File("bac_normalized_count.csv")
        sample = File("bac_sample_table.csv")
        mifaser = File("mifaser_dataset.csv")
        ec = File("ec_list_carbon.csv")
        params = File("flux_params.yml")

        # --- 16S community analysis (Figs 2, 3) ---
        asv_cliques = File("asv_cliques.rds"); asv_env = File("asv_clique_env.tsv")
        nmds = File("nmds.tsv"); adonis = File("adonis.tsv"); fig2 = File("fig2_nmds.pdf")
        rep_16s_job = (Job("rep_16s", _id="rep_16s", node_label="rep_16s")
                       .add_args(count, sample, asv_cliques, asv_env, nmds, adonis, fig2)
                       .add_inputs(count, sample)
                       .add_outputs(asv_cliques, asv_env, nmds, adonis, fig2,
                                    stage_out=True, register_replica=True))
        self.wf.add_jobs(rep_16s_job)

        # --- metagenome gene-cliques (Fig 4) ---
        gene_cliques = File("gene_cliques.rds"); gene_env = File("gene_clique_env.tsv")
        rep_mg_job = (Job("rep_metagenome", _id="rep_metagenome", node_label="rep_metagenome")
                      .add_args(mifaser, ec, sample, gene_cliques, gene_env)
                      .add_inputs(mifaser, ec, sample)
                      .add_outputs(gene_cliques, gene_env, stage_out=True, register_replica=True))
        self.wf.add_jobs(rep_mg_job)

        # --- carbon flux (Eqs 1-4) ---
        flux = File("carbon_flux.tsv")
        rep_flux_job = (Job("rep_carbon_flux", _id="rep_carbon_flux", node_label="rep_carbon_flux")
                        .add_args(sample, params, flux)
                        .add_inputs(sample, params)
                        .add_outputs(flux, stage_out=True, register_replica=True))
        self.wf.add_jobs(rep_flux_job)

        # --- report (convergence) ---
        report = File("report.html")
        report_job = (Job("make_report", _id="make_report", node_label="make_report")
                      .add_args(asv_env, gene_env, nmds, adonis, fig2, flux, report)
                      .add_inputs(asv_env, gene_env, nmds, adonis, fig2, flux)
                      .add_outputs(report, stage_out=True, register_replica=True))
        self.wf.add_jobs(report_job)
        return self.wf

    # --- Run Workflow ---------------------------------------------------------
    def run_workflow(self, execution_site_name, skip_sites_catalog, name,
                     plan=False, submit=False):
        if not skip_sites_catalog:
            print("Creating execution sites...")
            self.create_sites_catalog(execution_site_name)

        print("Creating workflow properties...")
        self.create_pegasus_properties()

        print("Creating transformation catalog...")
        self.create_transformation_catalog(execution_site_name)

        print("Creating replica catalog...")
        self.create_replica_catalog()

        print("Creating the SubductCR reproduce workflow dag...")
        self.create_workflow()

        self.write(name)
        print("Backend:", "SIF" if self.use_sif else "Docker",
              "| bypass_staging:", self.bypass)

        if plan:
            self.wf.plan(
                dir=os.path.join(self.wf_dir, "work"),
                sites=[execution_site_name],
                output_sites=["local"],
                submit=submit,
            )


if __name__ == '__main__':
    parser = ArgumentParser(description="Pegasus SubductCR Reproduce Workflow")
    parser.add_argument("-s", "--skip-sites-catalog", action="store_true",
                        help="Skip site catalog creation")
    parser.add_argument("-e", "--execution-site-name", metavar="STR", type=str,
                        default="condorpool",
                        help="Execution site (default: condorpool; use 'local' to run locally)")
    parser.add_argument("-o", "--output", metavar="STR", type=str,
                        default="workflow.yml", help="Output DAG file (default: workflow.yml)")
    parser.add_argument("--plan-only", action="store_true",
                        help="Plan the workflow but do not submit")
    parser.add_argument("--no-run", action="store_true",
                        help="Write catalogs + DAG only; do not plan")
    args = parser.parse_args()
    print(args)

    workflow = SubductCRReproduceWorkflow(dagfile=args.output)
    do_plan = not args.no_run
    do_submit = do_plan and not args.plan_only
    workflow.run_workflow(
        args.execution_site_name, args.skip_sites_catalog, args.output,
        plan=do_plan, submit=do_submit,
    )
    if args.no_run:
        print("Wrote catalogs + DAG. Skipping plan.")
    elif args.plan_only:
        print("Planned (not submitted). Submit with: pegasus-run <run-dir>")