#!/usr/bin/env bash
# run.sh — metagenome-to-model workflow. Pass --site, --test, --cpu as needed.
# Examples:
#   ./run.sh --site nersc                  full run on NERSC
#   ./run.sh --site usc                    full run on USC Laguna
#   ./run.sh --site usc --test             2-sample test on USC
#   ./run.sh --site usc --test --cpu       test, CPU-only
#   ./run.sh --site usc --plan-only        just plan
set -euo pipefail
cd "$(dirname "$0")"
export MAG_READS_DIR="${MAG_READS_DIR:-$(pwd)/data/metagenome}"
# databases (set to your cluster paths):
# export MAG_KOFAM_DB=/path/to/kofam_db
# export MAG_FUNC_DB=/path/to/mmseqs/uniref50
python3 workflow/metagenome_to_model.py "$@"
