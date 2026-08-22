#!/usr/bin/env bash
# =====================================================================
# run_all.sh -- one command to take the project from inputs to a running
# workflow on the cluster. Orchestrates the cluster-side stages:
#
#   1. fetch inputs     (invokes ./fetch_inputs.sh)
#   2. build .sif        (invokes ./containers/build_sif.sh)   [Route A]
#   3. plan + submit     (SUBDUCTCR_USE_SIF=1 python subductcr_workflow.py)
#
# Assumes the Docker images were already built + pushed to Docker Hub
# (run containers/build_and_push.sh on your Mac first). This script runs on
# the cluster login node.
#
# Usage (from the project root):
#   ./run_all.sh                 # fetch (no reads) -> build sif -> plan+submit
#   ./run_all.sh --with-reads    # also download SRA reads (needs sra-tools)
#   ./run_all.sh --plan-only      # stop after planning (do not submit)
#   ./run_all.sh --skip-fetch     # inputs already staged
#   ./run_all.sh --skip-sif       # .sif already built
#   ./run_all.sh --docker         # use Docker images instead of .sif
#   ./run_all.sh --threads 10
# =====================================================================
set -euo pipefail

WITH_READS=0; DO_FETCH=1; DO_SIF=1; DO_RUN=1; PLAN_ONLY=0; USE_DOCKER=0; THREADS=4
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-reads) WITH_READS=1; shift;;
    --skip-fetch) DO_FETCH=0; shift;;
    --skip-sif)   DO_SIF=0; shift;;
    --skip-run)   DO_RUN=0; shift;;
    --plan-only)  PLAN_ONLY=1; shift;;
    --docker)     USE_DOCKER=1; DO_SIF=0; shift;;
    --threads)    THREADS="$2"; shift 2;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown option: $1"; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# pick a python
PY=python3; command -v python3.11 >/dev/null 2>&1 && PY=python3.11
echo ">> project : $ROOT"
echo ">> python  : $PY ($($PY --version 2>&1))"

section(){ echo; echo "============================================================"; echo ">> $1"; echo "============================================================"; }

# ---- prereqs ----
command -v pegasus-version >/dev/null 2>&1 || { echo "ERROR: Pegasus not on PATH."; exit 1; }
if [[ $USE_DOCKER -eq 0 ]]; then
  command -v singularity >/dev/null 2>&1 || command -v apptainer >/dev/null 2>&1 \
    || { echo "ERROR: need singularity/apptainer for the .sif route (or pass --docker)."; exit 1; }
fi

# ---- 1. fetch inputs ----
if [[ $DO_FETCH -eq 1 ]]; then
  section "1/3  fetch inputs"
  if [[ $WITH_READS -eq 1 ]]; then
    if command -v prefetch >/dev/null 2>&1 && command -v esearch >/dev/null 2>&1; then
      ./fetch_inputs.sh --threads "$THREADS"
    else
      echo "WARN: --with-reads requested but sra-tools/entrez-direct missing;"
      echo "      staging everything except reads."
      ./fetch_inputs.sh --skip-reads --threads "$THREADS"
    fi
  else
    ./fetch_inputs.sh --skip-reads --threads "$THREADS"
  fi
else
  section "1/3  fetch inputs (skipped)"
fi

# ---- 2. build .sif ----
if [[ $DO_SIF -eq 1 ]]; then
  section "2/3  build .sif from Docker Hub images"
  if ls containers/sif/subductcr-*.sif >/dev/null 2>&1; then
    echo "   .sif already present in containers/sif/, skipping build"
  else
    ./containers/build_sif.sh swarmourr
  fi
else
  section "2/3  build .sif (skipped)"
fi

# ---- 3. plan + submit ----
section "3/3  plan the workflow"
RUN_ENV=()
if [[ $USE_DOCKER -eq 0 ]]; then export SUBDUCTCR_USE_SIF=1; echo "   backend: Singularity (.sif)"; else echo "   backend: Docker Hub images"; fi

if [[ $DO_RUN -eq 0 ]]; then
  echo "   --skip-run: writing catalogs only"
  $PY subductcr_workflow.py --no-run
elif [[ $PLAN_ONLY -eq 1 ]]; then
  $PY subductcr_workflow.py --plan-only
else
  $PY subductcr_workflow.py
fi

section "done"
cat <<EOF
Monitor / manage the run (path printed above by pegasus-plan):
  pegasus-status  -w <run-dir>
  pegasus-analyzer   <run-dir>     # if a job fails
  pegasus-statistics <run-dir>     # after completion
EOF
