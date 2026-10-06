#!/usr/bin/env bash
# =============================================================================
# prepare_data.sh  —  check existing data, download only what's missing,
#                     and normalize every filename to the workflow's convention
# =============================================================================
# Makes the project self-healing:
#   1. CHECK   — look in your existing data folder(s) for each required file
#   2. NORMALIZE — rename/symlink to the canonical names the workflow expects
#   3. DOWNLOAD — fetch only the files that are genuinely missing
#
# Canonical names the workflow uses:
#   data/metagenome/<SAMPLE>_R1.fastq.gz   <SAMPLE>_R2.fastq.gz
#   data/16s/<SAMPLE>_R1.fastq.gz          <SAMPLE>_R2.fastq.gz   (optional)
#   data/reference/silva_v132.db  silva_v132.tax
#   data/reference/geochem.csv  cell_counts.csv  ec_carbon.csv
#
# Your files may be named differently (e.g. CYF_MG_R1.fastq.gz,
# silva.nr_v132.align); this script maps them automatically.
#
# Usage:
#   ./bin/prepare_data.sh /path/to/existing/input     # use your data, fetch gaps
#   ./bin/prepare_data.sh                             # download everything fresh
#   ./bin/prepare_data.sh /path/to/input --check      # report only, no changes
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-}"                                   # optional existing data folder
CHECK_ONLY=0; [ "${2:-}" = "--check" ] && CHECK_ONLY=1
MG="$ROOT/data/metagenome"; S16="$ROOT/data/16s"; REF="$ROOT/data/reference"
SRCREF="$ROOT/reference_data"
mkdir -p "$MG" "$S16" "$REF"

log(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok(){  printf '   \033[32m✓\033[0m %s\n' "$*"; }
dl(){  printf '   \033[36m↓\033[0m %s\n' "$*"; }
miss(){ printf '   \033[33m•\033[0m %s\n' "$*"; }

# the 35 metagenome sample codes the workflow expects
MG_SAMPLES="ARS BQF BQS BR1F BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETS FAS MTF \
PBS PFF PFS PGF PGS PLS QH2F QHS1 QHS2 QNF QNS RSF RSS RVF SIF SIS SLF SLS TCF TCS"

# -----------------------------------------------------------------------------
# helper: find a sample's read file in SRC under any of several naming patterns
#   tries:  <S>_R1  <S>_MG_R1  <S><date>_MG_R1
# -----------------------------------------------------------------------------
find_read() {
  local sample="$1" read="$2" dir="$3"     # sample, R1|R2, search dir
  [ -z "$dir" ] && return 1
  local cand
  for pat in "${sample}_${read}.fastq.gz" \
             "${sample}_MG_${read}.fastq.gz" \
             "${sample}"*"_MG_${read}.fastq.gz"; do
    cand=$(ls "$dir"/$pat 2>/dev/null | head -1 || true)
    [ -n "$cand" ] && { echo "$cand"; return 0; }
  done
  return 1
}

link_or_copy() {   # src dst   (absolute symlink to save space; copy if cross-device)
  local src dst
  src="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"   # resolve to absolute
  dst="$2"
  [ -e "$dst" ] && return 0
  ln -sf "$src" "$dst" 2>/dev/null || cp "$src" "$dst"
}

# =============================================================================
# 1. METAGENOME READS
# =============================================================================
prepare_reads() {
  log "Metagenome reads  (check -> normalize -> download gaps)"
  local have=0 linked=0 missing=""
  for s in $MG_SAMPLES; do
    local d1="$MG/${s}_R1.fastq.gz" d2="$MG/${s}_R2.fastq.gz"
    if [ -f "$d1" ] && [ -f "$d2" ]; then ok "$s (present)"; have=$((have+1)); continue; fi
    # look in the user's source folder under any naming
    if [ -n "$SRC" ]; then
      local f1 f2
      f1=$(find_read "$s" R1 "$SRC" || true)
      f2=$(find_read "$s" R2 "$SRC" || true)
      if [ -n "$f1" ] && [ -n "$f2" ]; then
        if [ "$CHECK_ONLY" = "0" ]; then
          link_or_copy "$f1" "$d1"; link_or_copy "$f2" "$d2"
        fi
        ok "$s (from $(basename "$f1") -> ${s}_R1.fastq.gz)"; linked=$((linked+1)); continue
      fi
    fi
    missing="$missing $s"
  done
  echo "   ---"
  ok "$have already normalized, $linked linked from source"
  if [ -n "$missing" ]; then
    miss "missing:$missing"
    [ "$CHECK_ONLY" = "1" ] && return
    log "Downloading missing metagenome reads from ENA"
    download_reads "$missing"
  fi
}

download_reads() {
  local want="$1"
  # build the ENA sample->fastq map if not present
  if [ ! -f "$REF/ena_map.tsv" ]; then
    curl -fSL --retry 3 -o "$REF/ena_raw.tsv" \
      "https://www.ebi.ac.uk/ena/portal/api/filereport?accession=PRJNA627197&result=read_run&format=tsv&fields=run_accession,library_name,fastq_ftp"
    python3 - "$REF/ena_raw.tsv" "$REF/ena_map.tsv" <<'PY'
import sys,re,csv
raw,out=sys.argv[1],sys.argv[2]
KNOWN=set("ARS BQF BQS BQS1 BR1F BRF1 BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETF ETS FAF FAS MTF PBS PFF PFS PGF PGS PLS QHF2 QH2F QHS1 QHS2 QNF QNS RSF RSS RVF SIF SIS SLF SLS STS TCF TCS VCS".split())
def code(l):
    fi=l.split('_')[0];m=re.match(r'^(.*?)(\d{6})$',fi);h=m.group(1) if m else fi
    if h in KNOWN:return h
    if fi in KNOWN:return fi
    for k in sorted(KNOWN,key=len,reverse=True):
        if l.startswith(k):return k
    return h or l
w=csv.writer(open(out,"w"),delimiter="\t");w.writerow(["sample","run","ftp"])
r=csv.reader(open(raw),delimiter="\t");next(r,None)
for row in r:
    if len(row)>=3: w.writerow([code(row[1]),row[0],row[2]])
PY
  fi
  for s in $want; do
    local line; line=$(grep -P "^${s}\t" "$REF/ena_map.tsv" | head -1 || true)
    [ -z "$line" ] && { miss "$s: not found in ENA map"; continue; }
    local ftp; ftp=$(echo "$line" | cut -f3)
    local r1 r2; r1=$(echo "$ftp"|cut -d';' -f1); r2=$(echo "$ftp"|cut -d';' -f2)
    [ -z "$r1" ] && { miss "$s: no fastq listed"; continue; }
    dl "$s"
    curl -fSL --retry 3 -o "$MG/${s}_R1.fastq.gz" "https://$r1"
    curl -fSL --retry 3 -o "$MG/${s}_R2.fastq.gz" "https://$r2"
  done
}

# =============================================================================
# 2. SILVA REFERENCE  (handle silva.nr_v132.align / silva_v132.db naming)
# =============================================================================
prepare_silva() {
  log "SILVA reference (always re-downloaded fresh, to be sure)"
  # By design we do NOT reuse a local SILVA — we always pull the canonical
  # mothur release so the reference is guaranteed correct and complete.
  if [ "$CHECK_ONLY" = "1" ]; then
    miss "would re-download SILVA v132 from mothur (~600 MB)"; return
  fi
  dl "downloading SILVA v132 from mothur (~600 MB, fresh)"
  curl -fSL --retry 3 -o "$REF/silva.tgz" \
    "https://mothur.s3.us-east-2.amazonaws.com/wiki/silva.nr_v132.tgz"
  # verify the download is a real gzip archive before trusting it
  if ! gzip -t "$REF/silva.tgz" 2>/dev/null; then
    printf '   \033[31m✗\033[0m SILVA download is not a valid archive — aborting\n'
    rm -f "$REF/silva.tgz"; return 1
  fi
  tar -xzf "$REF/silva.tgz" -C "$REF"
  mv -f "$REF"/silva.nr_v132.align "$REF/silva_v132.db"
  mv -f "$REF"/silva.nr_v132.tax   "$REF/silva_v132.tax"
  rm -f "$REF/silva.tgz"
  local n; n=$(grep -c '^>' "$REF/silva_v132.db" 2>/dev/null || echo "?")
  ok "silva_v132.db ($n reference sequences) + silva_v132.tax"
}

# =============================================================================
# 3. REFERENCE TABLES  (geochem, cell_counts, ec_carbon, flux_params)
# =============================================================================
prepare_tables() {
  log "Reference tables"
  if [ "$CHECK_ONLY" = "0" ]; then
    stage_bundled_tables
  else
    [ -f "$SRCREF/ec_carbon.csv" ] && ok "reference_data/ec_carbon.csv" || miss "reference_data/ec_carbon.csv missing"
    [ -f "$SRCREF/geochem.csv" ] && ok "reference_data/geochem.csv" || miss "reference_data/geochem.csv missing"
  fi
  [ -f "$REF/ec_carbon.csv" ] && ok "ec_carbon.csv (present)" || miss "ec_carbon.csv will be staged from reference_data"
  # geochem.csv + cell_counts.csv: take from SRC if present, else derive from reference_data/geochem.csv
  for f in geochem.csv cell_counts.csv; do
    if [ -f "$REF/$f" ]; then ok "$f (present)"; continue; fi
    if [ -n "$SRC" ] && [ -f "$SRC/$f" ]; then
      [ "$CHECK_ONLY" = "0" ] && cp "$SRC/$f" "$REF/$f"; ok "$f (from source)"
    else
      miss "$f will be built from reference_data/geochem.csv"
    fi
  done
  # flux_params.yml -> config/
  if [ -n "$SRC" ] && [ -f "$SRC/flux_params.yml" ] && [ ! -f "$ROOT/config/flux_params.yml" ]; then
    [ "$CHECK_ONLY" = "0" ] && cp "$SRC/flux_params.yml" "$ROOT/config/flux_params.yml"; ok "flux_params.yml (from source)"
  else
    [ -f "$ROOT/config/flux_params.yml" ] && ok "flux_params.yml (present)"
  fi
  if [ "$CHECK_ONLY" = "0" ]; then
    stage_bundled_tables
  fi
}

stage_bundled_tables() {
  if [ -f "$SRCREF/ec_carbon.csv" ]; then
    cp "$SRCREF/ec_carbon.csv" "$REF/ec_carbon.csv"
  fi
  [ -f "$REF/geochem.csv" ] && [ -f "$REF/cell_counts.csv" ] && return 0
  [ -f "$SRCREF/geochem.csv" ] || return 0
  cp "$SRCREF/geochem.csv" "$REF/geochem.csv"
  python3 - "$SRCREF/geochem.csv" "$REF/cell_counts.csv" <<'PY'
import sys,csv
src,out=sys.argv[1:3]
with open(src,newline="") as fi, open(out,"w",newline="") as fo:
    r=csv.DictReader(fi)
    if not r.fieldnames:
        raise SystemExit("geochem.csv has no header")
    sample_col="sample" if "sample" in r.fieldnames else r.fieldnames[0]
    cell_col=next((c for c in r.fieldnames if c.lower()=="cells_flu"), None)
    if cell_col is None:
        cell_col=next((c for c in r.fieldnames if "cell" in c.lower()), None)
    if cell_col is None:
        raise SystemExit("no cell-count column found in geochem.csv")
    w=csv.writer(fo)
    w.writerow(["sample","cells_per_ml"])
    for row in r:
        w.writerow([row[sample_col],row[cell_col]])
print("   staged geochem.csv + cell_counts.csv from reference_data")
PY
  ok "staged bundled geochemistry and cell counts"
}

# =============================================================================
# 4. 16S reads (optional — only if you want the from-reads 16S branch)
# =============================================================================
prepare_16s() {
  log "16S reads (optional)"
  [ -z "$SRC" ] && { miss "no source given; 16S branch will use KEBJ01 if configured"; return; }
  local n=0
  for f in "$SRC"/*_16S_R1.fastq.gz; do
    [ -e "$f" ] || break
    local s; s=$(basename "$f" _16S_R1.fastq.gz)
    if [ "$CHECK_ONLY" = "0" ]; then
      link_or_copy "$f" "$S16/${s}_R1.fastq.gz"
      link_or_copy "${f%_R1.fastq.gz}_R2.fastq.gz" "$S16/${s}_R2.fastq.gz"
    fi
    n=$((n+1))
  done
  [ "$n" -gt 0 ] && ok "$n 16S read pairs normalized" || miss "no 16S reads in source"
}

# =============================================================================
# run
# =============================================================================
[ -n "$SRC" ] && log "Source folder: $SRC" || log "No source folder — will download everything"
[ "$CHECK_ONLY" = "1" ] && log "CHECK-ONLY mode (no changes made)"

prepare_reads
prepare_silva
prepare_tables
prepare_16s

log "Data preparation complete."
echo "   metagenome reads : $(ls "$MG"/*_R1.fastq.gz 2>/dev/null | wc -l) / 35"
echo "   16S reads        : $(ls "$S16"/*_R1.fastq.gz 2>/dev/null | wc -l) pairs"
echo "   SILVA            : $([ -f "$REF/silva_v132.db" ] && echo present || echo MISSING)"
echo "   env tables       : $([ -f "$REF/geochem.csv" ] && echo present || echo 'run get_data.sh geochem')"
echo ""
echo "   next:  make plan   &&   make run"
