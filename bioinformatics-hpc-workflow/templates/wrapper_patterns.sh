#!/usr/bin/env bash
# ============================================================================
# WRAPPER PATTERNS — conventions proven across real HPC bioinformatics runs.
# Each pattern exists because NOT doing it caused a real failure. See the
# gotchas reference for the story behind each.
# ============================================================================

# --- PATTERN 1: absolute paths (tools cd internally) -----------------------
# mothur, DAS Tool, MMseqs and others change directory internally, so relative
# paths from the Pegasus working dir get lost. Resolve EVERY input and output
# to an absolute path first.
#   IN="$(readlink -f "$1")"
#   OUT_DIR="$(cd "$(dirname "$2")" && pwd)"; OUT="$OUT_DIR/$(basename "$2")"

# --- PATTERN 2: SIGPIPE-safe pipes (exit 141) ------------------------------
# `set -euo pipefail` + a pipe whose reader closes early (zcat | head) dies
# with SIGPIPE (141). Drop -e for that step, or absorb the pipe, or use seqtk.
#   set -uo pipefail                           # NOTE: no -e
#   { zcat "$in" 2>/dev/null | head -n "$N" || true; } | gzip > "$out"
#   # better, if available:  seqtk sample -s100 "$in" "$N" | gzip > "$out"

# --- PATTERN 3: guard empty inputs (valid "nothing" outcomes) --------------
# A step can legitimately receive nothing (binning on sparse data -> empty
# MAGs). Don't crash the downstream job — write an empty output and exit 0 so
# the DAG continues.
#   if [ ! -s "$MG" ] || ! grep -q "^>" "$MG" 2>/dev/null; then
#     printf "header\tcols\n" > "$OUT"; echo "[step] empty input — exit clean"; exit 0
#   fi

# --- PATTERN 4: GPU flag only when GPU is truly on -------------------------
# ${VAR:+flag} adds the flag when VAR is NON-EMPTY — so VAR=0 still adds it!
# Check for =1 explicitly.
#   GPUFLAG=""; [ "${USE_GPU:-1}" = "1" ] && GPUFLAG="--engine gpu"
#   sometool ... $GPUFLAG

# --- PATTERN 5: reference DB path defaults to shared storage (not home) ----
# Container runtimes (Shifter/Apptainer) don't mount home. Default DB paths to
# a mounted filesystem (CFS/scratch).
#   DB="${FUNC_DB:-/global/cfs/cdirs/<proj>/<user>/refs/uniref50}"

# --- PATTERN 6: no python dependency when a container may lack it -----------
# Don't assume python3 is in every container. Use awk for simple text work.
#   awk -v b="$b" '/^>/{print ">"b"__"substr($0,2); next} {print}' "$f"

# --- PATTERN 7: robust mothur dereplication (ASV table) --------------------
# unique.seqs can over-collapse (1.3M seqs -> 1 ASV) or need a group file
# count.seqs can't resolve. Dereplicating by exact sequence identity in a
# small script (or seqkit rmdup) is more reliable than fighting the tool, and
# counts per sample from the header. The lesson: match the authors' METHOD
# (dereplicate + per-sample counts), but reach it by the most reliable route.

# --- PATTERN 8: ID matching for functional/metal search --------------------
# The annotation output ID type MUST match the reference gene list. KO list +
# UniRef hits = zero matches. Route the metal/function search through the
# annotator that emits the SAME id type (KOfam -> KOs to match a KO list).

# --- PATTERN 9: logging for diagnosis --------------------------------------
# Log inputs, sizes, counts, and tool exit codes. When a job fails on the
# cluster, the log is all you have.
#   log(){ echo "[step $(date +%H:%M:%S)] $*"; }
#   log "input: $(grep -c '^>' "$IN") sequences"
