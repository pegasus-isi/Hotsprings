#!/usr/bin/env bash
# run_test.sh — launch the small test workflow (3 samples, subsampled reads)
set -euo pipefail
cd "$(dirname "$0")"

# --- NERSC / Perlmutter settings (same as run.sh) ---
export MAG_USE_SHIFTER=1
export MAG_TAG=latest
export RESOURCE_PROJECT=m4144
export RESOURCE_USERNAME=hsafri
export RESOURCE_SCRATCH_DIR="${PSCRATCH:-/pscratch/sd/h/hsafri}"
export SSH_PRIVATE_KEY="$HOME/.ssh/nersc"
export MAG_GPU=1

# --- reads folder (same real reads as the full run) ---
export MAG_READS_DIR="$(pwd)/data/metagenome"

# --- test: 3 samples with geochemistry coverage, 500k read-pair subsample ---
export MAG_TEST_SAMPLES="${MAG_TEST_SAMPLES:-CYF SLS TCF}"
export MAG_SUBSAMPLE="${MAG_SUBSAMPLE:-500000}"

# --- databases (must be set before running) ---
# export MAG_FUNC_DB=/path/to/mmseqs/uniref   # not used in test (mmseqs_func removed)
# (DRAM databases configured via dram-setup.py on the cluster)

echo "Test workflow: samples=${MAG_TEST_SAMPLES}  subsample=${MAG_SUBSAMPLE} pairs"
python3 workflow/test_metagenome_to_model.py "$@"
