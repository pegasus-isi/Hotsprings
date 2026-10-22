#!/usr/bin/env python3
"""Skeleton: portable bioinformatics Pegasus workflow.
Fill in TOOLS (from tool_selection), SAMPLES, and the job wiring.
SITE profile makes it portable across HPC systems."""
import os, glob, argparse
from pathlib import Path
from Pegasus.api import (Workflow, Job, File, Container, Transformation,
    TransformationCatalog, ReplicaCatalog, Properties, Namespace)

ROOT = Path(__file__).resolve().parent.parent
BIN, DATA, REF = ROOT/"bin", ROOT/"data", ROOT/"data"/"reference"
READS = Path(os.environ.get("READS_DIR", str(DATA/"reads")))

# ---- SITE PROFILE (portability) ----
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
USE_GPU = os.environ.get("USE_GPU", "1") == "1"

def make_containers(user="myns", tag="latest"):
    def c(name, image):
        if SITE["runtime"] == "shifter":
            return Container(name, Container.SHIFTER, image=f"shifter:///{image}", bypass_staging=True)
        if SITE["runtime"] == "singularity":
            return Container(name, Container.SINGULARITY,
                             image=f"file://{ROOT/'containers'/'sif'/(name+'.sif')}", image_site="local")
        return Container(name, Container.DOCKER, image=f"docker://{image}")
    # TODO: one per tool family
    return {n: c(f"tool-{n}", f"{user}/tool-{n}:{tag}") for n in ["qc","assembly","binning","annot","r"]}

def T(tc, name, container, mem_gb=32, cpus=16, gpus=0, runtime=86400):
    t = Transformation(name, site="local", pfn=str(BIN/name), is_stageable=True, container=container)
    for k,v in [("memory",mem_gb*1024),("cores",cpus),("runtime",runtime),("maxwalltime",runtime//60)]:
        t.add_profiles(Namespace.PEGASUS, key=k, value=str(v))
    want_gpu = bool(gpus) and USE_GPU
    t.add_profiles(Namespace.PEGASUS, key="queue", value=SITE["gpu_queue"] if want_gpu else SITE["cpu_queue"])
    if want_gpu:
        t.add_profiles(Namespace.PEGASUS, key="gpus", value=str(gpus))
        if SITE["gpu_arg"]: t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=SITE["gpu_arg"])
    elif SITE["cpu_arg"]:
        t.add_profiles(Namespace.PEGASUS, key="glite.arguments", value=SITE["cpu_arg"])
    tc.add_transformations(t); return t

def make_properties():
    p = Properties()
    p["dagman.retry"] = "3"
    p["pegasus.integrity.checking"] = "none"              # wrapper edits don't need checksum updates
    p["pegasus.transfer.worker.package.autodownload"] = "false"   # containers without curl still work
    p["dagman.maxjobs"] = "20"
    return p

# TODO: make_replicas(samples), build_workflow(T, samples) with per-sample
# fan-out + a single merge/predict convergence, then plan with
# sites=[SITE["exec_site"]], output_sites=["local"].
