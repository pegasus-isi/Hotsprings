#!/usr/bin/env bash
# Build + push the three SubductCR container images.
# Usage:  ./containers/build.sh  [dockerhub-namespace]
set -euo pipefail
NS="${1:-swarmourr}"
cd "$(dirname "$0")"
for tool in r mothur mifaser qc; do
  [ -f "Dockerfile.$tool" ] || continue
  echo "=== building subductcr-$tool ==="
  docker build --platform linux/amd64 -t "$NS/subductcr-$tool:1.0" -f "Dockerfile.$tool" .
  # check R image loads its libraries before pushing
  if [ "$tool" = "r" ]; then
    docker run --rm "$NS/subductcr-$tool:1.0" \
      R -e 'stopifnot(all(sapply(c("phyloseq","vegan","igraph","ggplot2","yaml"), requireNamespace, quietly=TRUE)))'
  fi
  docker push "$NS/subductcr-$tool:1.0"
done
echo "done."
