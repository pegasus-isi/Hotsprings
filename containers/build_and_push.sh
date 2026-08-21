#!/usr/bin/env bash
# =====================================================================
# build_and_push.sh
# Build all four SubductCR container images for linux/amd64, tag them
# under your Docker Hub namespace, and push.
#
# Usage:
#   ./containers/build_and_push.sh YOURUSER            # build + push
#   DOCKER_USER=YOURUSER ./containers/build_and_push.sh
#   ./containers/build_and_push.sh YOURUSER --tag 1.1  # custom version tag
#   ./containers/build_and_push.sh YOURUSER --no-push  # build only, no push
#   ./containers/build_and_push.sh YOURUSER --sif      # also print .sif build cmds
#
# Run from the project root (the directory that contains containers/).
# =====================================================================
set -euo pipefail

# ---- args ----
DOCKER_USER="${1:-${DOCKER_USER:-}}"
TAG="1.0"; DO_PUSH=1; PRINT_SIF=0
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) TAG="$2"; shift 2;;
    --no-push) DO_PUSH=0; shift;;
    --sif) PRINT_SIF=1; shift;;
    *) echo "unknown option: $1"; exit 1;;
  esac
done

if [[ -z "$DOCKER_USER" ]]; then
  echo "ERROR: Docker Hub username required."
  echo "  usage: $0 YOURUSER   (or set DOCKER_USER=YOURUSER)"
  exit 1
fi

# ---- locate project root (parent of this script's dir) ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
echo ">> project root: $ROOT"
echo ">> docker user : $DOCKER_USER    tag: $TAG"

# ---- Apple-Silicon guard: always target the cluster's arch ----
PLATFORM="linux/amd64"
HOST_ARCH="$(uname -m)"
echo ">> host arch    : $HOST_ARCH  ->  building for $PLATFORM"

# image names (under your namespace)
R_IMG="$DOCKER_USER/subductcr-r:$TAG"
QC_IMG="$DOCKER_USER/subductcr-qc:$TAG"
MOTHUR_IMG="$DOCKER_USER/subductcr-mothur:$TAG"
MIFASER_IMG="$DOCKER_USER/subductcr-mifaser:$TAG"

# upstream sources for the two we only re-tag
MOTHUR_SRC="dnastack/mothur:1.48.0"
MIFASER_SRC="bromberglab/mifaser:latest"

# ---- preflight ----
command -v docker >/dev/null || { echo "ERROR: docker not found. Start Docker Desktop."; exit 1; }
docker info >/dev/null 2>&1 || { echo "ERROR: Docker daemon not running. Start Docker Desktop."; exit 1; }

# ensure the qc Dockerfile exists (trimmomatic + vsearch for qc_16s)
if [[ ! -f containers/Dockerfile.qc ]]; then
  echo ">> creating containers/Dockerfile.qc (trimmomatic + vsearch)"
  cat > containers/Dockerfile.qc <<'EOF'
FROM staphb/trimmomatic:0.39
RUN apt-get update && apt-get install -y vsearch && rm -rf /var/lib/apt/lists/*
EOF
fi

# ---- 1. build the three images we own (R, QC, mothur) ----
echo; echo "==> [1/4] build R image:      $R_IMG"
docker build --platform "$PLATFORM" -t "$R_IMG" -f containers/Dockerfile.r .

echo; echo "==> [2/4] build QC image:     $QC_IMG"
docker build --platform "$PLATFORM" -t "$QC_IMG" -f containers/Dockerfile.qc .

# mothur is built from bioconda (clean pinned tag; biocontainers hashed tags
# like 1.48.0--hdbcae75_0 are fragile and often unknown).
echo; echo "==> [3/4] build mothur image: $MOTHUR_IMG"
docker build --platform "$PLATFORM" -t "$MOTHUR_IMG" -f containers/Dockerfile.mothur .

# ---- 2. pull + re-tag the one upstream image (mifaser is published amd64) ----
echo; echo "==> [4/4] pull + tag mifaser: $MIFASER_SRC -> $MIFASER_IMG"
docker pull --platform "$PLATFORM" "$MIFASER_SRC"
docker tag "$MIFASER_SRC" "$MIFASER_IMG"

# ---- 3. verify architecture (catch the Apple-Silicon arm64 trap) ----
echo; echo "==> verifying image architectures (must be amd64):"
FAIL=0
for img in "$R_IMG" "$QC_IMG" "$MOTHUR_IMG" "$MIFASER_IMG"; do
  arch="$(docker image inspect "$img" --format '{{.Architecture}}' 2>/dev/null || echo '?')"
  printf "   %-40s %s\n" "$img" "$arch"
  [[ "$arch" == "amd64" ]] || FAIL=1
done
if [[ $FAIL -ne 0 ]]; then
  echo "ERROR: at least one image is not amd64. Rebuild with --platform linux/amd64."
  exit 1
fi

# ---- 4. push ----
if [[ $DO_PUSH -eq 1 ]]; then
  echo; echo "==> logging in to Docker Hub (skip if already logged in)"
  docker login
  echo; echo "==> pushing all four images"
  for img in "$R_IMG" "$QC_IMG" "$MOTHUR_IMG" "$MIFASER_IMG"; do
    echo "   push $img"; docker push "$img"
  done
  echo; echo "DONE. Images live at:"
  for img in "$R_IMG" "$QC_IMG" "$MOTHUR_IMG" "$MIFASER_IMG"; do echo "   docker://$img"; done
else
  echo; echo "Built (not pushed, --no-push). Images:"
  for img in "$R_IMG" "$QC_IMG" "$MOTHUR_IMG" "$MIFASER_IMG"; do echo "   $img"; done
fi

# ---- 5. next-steps hint: wire these into the generator ----
echo
echo "Next: set these in subductcr_workflow.py -> build_containers():"
echo "   mothur_c  = Container(\"mothur_ctr\",  Container.DOCKER, image=\"docker://$MOTHUR_IMG\")"
echo "   bio_c     = Container(\"bio_ctr\",     Container.DOCKER, image=\"docker://$QC_IMG\")"
echo "   mifaser_c = Container(\"mifaser_ctr\", Container.DOCKER, image=\"docker://$MIFASER_IMG\")"
echo "   r_c       = Container(\"r_ctr\",       Container.DOCKER, image=\"docker://$R_IMG\")"

# ---- optional: print Singularity/.sif build commands for the cluster ----
if [[ $PRINT_SIF -eq 1 ]]; then
  echo
  echo "On the cluster (login node with internet), build .sif files with:"
  echo "   singularity build subductcr-r.sif       docker://$R_IMG"
  echo "   singularity build subductcr-qc.sif       docker://$QC_IMG"
  echo "   singularity build subductcr-mothur.sif   docker://$MOTHUR_IMG"
  echo "   singularity build subductcr-mifaser.sif  docker://$MIFASER_IMG"
  echo "Then switch the generator entries to Container.SINGULARITY with file:///abs/path/*.sif"
fi
