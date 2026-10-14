#!/usr/bin/env bash
# run.sh — set up env + launch the metagenome-to-model workflow
set -euo pipefail
cd "$(dirname "$0")"

# --- NERSC / Perlmutter settings ---
export MAG_USE_SHIFTER=1
export MAG_TAG=latest
export RESOURCE_PROJECT=m4144
export RESOURCE_USERNAME=hsafri
export RESOURCE_SCRATCH_DIR="${PSCRATCH:-/pscratch/sd/h/hsafri}"
export SSH_PRIVATE_KEY="$HOME/.ssh/nersc"

# --- GPU for the deep-learning + MMseqs2 jobs ---
export MAG_GPU=1

# --- reads folder (your real metagenome reads) ---
export MAG_READS_DIR="$(pwd)/data/metagenome"

# --- auto-detect samples from the reads folder (override the baked-in 34) ---
if ls data/metagenome/*_R1.fastq.gz >/dev/null 2>&1; then
  export MAG_METAGENOMES="$(ls data/metagenome/*_R1.fastq.gz | sed 's|.*/||;s|_R1.*||' | tr '\n' ' ')"
  echo "samples: $MAG_METAGENOMES"
fi

# --- databases (set these to your cluster paths) ---
# export MAG_FUNC_DB=/path/to/mmseqs/uniref
# export GTDBTK_DATA_PATH=/path/to/gtdb
# (DRAM databases configured via DRAM setup)

# --- launch ---
python3 workflow/metagenome_to_model.py "$@"
