#!/usr/bin/env bash
# =====================================================================
# build_sif.sh  (Route A: build .sif from your Docker Hub images)
#
# Pulls the four SubductCR images from Docker Hub and converts each into a
# Singularity/Apptainer .sif, written to containers/sif/ -- exactly where
# subductcr_workflow.py looks when SUBDUCTCR_USE_SIF=1.
#
# Run this ON THE CLUSTER login node (has internet + Singularity/Apptainer,
# same CPU arch as the compute nodes). Run AFTER build_and_push.sh has pushed
# the images.
#
# Usage:
#   ./containers/build_sif.sh                 # user=swarmourr tag=1.0 -> containers/sif/
#   ./containers/build_sif.sh YOURUSER        # different Docker Hub user
#   ./containers/build_sif.sh YOURUSER 1.1    # different tag
#   SIF_OUT=/scratch/$USER/sif ./containers/build_sif.sh   # custom output dir
# =====================================================================
set -euo pipefail

DOCKER_USER="${1:-${DOCKER_USER:-swarmourr}}"
TAG="${2:-${TAG:-1.0}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# default output = the directory the workflow looks for (containers/sif)
SIF_OUT="${SIF_OUT:-$ROOT/containers/sif}"
mkdir -p "$SIF_OUT"

# pick Singularity or Apptainer, whichever is installed
if command -v singularity >/dev/null 2>&1; then
  SING=singularity
elif command -v apptainer >/dev/null 2>&1; then
  SING=apptainer
else
  echo "ERROR: neither 'singularity' nor 'apptainer' found on PATH."
  echo "  Load the module first, e.g.  module load singularity   (or apptainer)"
  exit 1
fi

echo ">> using       : $SING ($($SING --version 2>/dev/null | head -1))"
echo ">> docker user : $DOCKER_USER    tag: $TAG"
echo ">> output dir  : $SIF_OUT"
echo

# tool key -> .sif filename (matches subductcr-<tool>.sif in the generator)
TOOLS=(mothur qc mifaser r)

for tool in "${TOOLS[@]}"; do
  src="docker://$DOCKER_USER/subductcr-$tool:$TAG"
  out="$SIF_OUT/subductcr-$tool.sif"
  echo "==> building $out"
  echo "    from $src"
  # --force overwrites a stale .sif; drop it to keep existing files
  $SING build --force "$out" "$src"
  echo
done

echo "DONE. .sif files:"
ls -la "$SIF_OUT"/subductcr-*.sif

cat <<EOF

Next: run the workflow using these .sif files instead of Docker:

  export SUBDUCTCR_USE_SIF=1
  python3.11 subductcr_workflow.py

The generator reads SIF_DIR = $ROOT/containers/sif by default. If you built the
.sif somewhere else (SIF_OUT above), either symlink them into containers/sif/ or
edit SIF_DIR near the top of subductcr_workflow.py to point at $SIF_OUT.
EOF
