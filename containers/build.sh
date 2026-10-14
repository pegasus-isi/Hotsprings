#!/usr/bin/env bash
set -euo pipefail
NS="${1:-swarmourr}"; TAG="${2:-latest}"; cd "$(dirname "$0")"
for df in Dockerfile.*; do
  tool="${df#Dockerfile.}"; img="$NS/mag-$tool:$TAG"
  echo "=== $img ==="; docker build --platform linux/amd64 -t "$img" -f "$df" . && docker push "$img"
done
echo "done"
