# Containers

Four images, one per tool family (declared in `subductcr_workflow.py`).

| Transformation(s)    | Image (Docker Hub, swarmourr namespace) | Built by            |
|----------------------|------------------------------------------|---------------------|
| qc_16s, trim_reads   | `swarmourr/subductcr-qc:1.0`             | Dockerfile.qc       |
| mothur_asv           | `swarmourr/subductcr-mothur:1.0`         | Dockerfile.mothur   |
| mifaser              | `swarmourr/subductcr-mifaser:1.0`        | re-tag of upstream  |
| all R jobs           | `swarmourr/subductcr-r:1.0`              | Dockerfile.r        |

## 1. Build + push Docker images

    ./containers/build_and_push.sh swarmourr

Builds R, QC (trimmomatic + vsearch), and mothur (from bioconda) for
linux/amd64, re-tags the published `bromberglab/mifaser:latest`, arch-checks
all four, and pushes to Docker Hub. Flags: `--no-push`, `--tag X`, `--sif`.

## 2A. Run with Docker (default)

If your compute nodes can reach Docker Hub, nothing else is needed:

    python3 subductcr_workflow.py

## 2B. Run with Singularity/Apptainer .sif (Route A, typical HPC)

Build .sif from the pushed Hub images, then flip the toggle:

    ./containers/build_sif.sh swarmourr      # writes containers/sif/*.sif
    export SUBDUCTCR_USE_SIF=1
    python3 subductcr_workflow.py

`build_sif.sh` auto-detects `singularity` vs `apptainer` and writes into
`containers/sif/`, which is exactly the directory the generator reads
(`SIF_DIR`) when `SUBDUCTCR_USE_SIF=1`. Run it on a cluster login node with
internet and the same CPU arch as the compute nodes.

Custom output location:

    SIF_OUT=/scratch/$USER/sif ./containers/build_sif.sh swarmourr
    # then point SIF_DIR in subductcr_workflow.py at /scratch/$USER/sif
