#!/usr/bin/env bash
# =============================================================================
# setup_data.sh  —  ONE script to get all workflow data ready
# =============================================================================
# For each required input it will, in order:
#     1. CHECK   is it already in place (and valid)?          -> skip
#     2. FIND    is it in your existing data folder?          -> move + rename
#     3. DOWNLOAD otherwise fetch it from the public archive
#     4. VERIFY  confirm the file is real and non-empty
#
# Everything ends up as REAL FILES under data/ (no fragile symlinks), named the
# way the workflow expects.
#
# Usage:
#   ./bin/setup_data.sh ../input       # use your existing data, fetch the rest
#   ./bin/setup_data.sh                # download everything fresh
#   ./bin/setup_data.sh ../input --check   # report only, change nothing
#   ./bin/setup_data.sh ../input --copy    # copy instead of move (keeps input/)
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_ARG="${1:-}"
MODE_MOVE="mv"                                   # default: move (fast, no dup)
CHECK_ONLY=0
for a in "$@"; do
  [ "$a" = "--check" ] && CHECK_ONLY=1
  [ "$a" = "--copy" ]  && MODE_MOVE="cp"
done
# resolve SRC to an absolute path if given and it's a real dir
SRC=""
if [ -n "$SRC_ARG" ] && [ "${SRC_ARG#--}" = "$SRC_ARG" ] && [ -d "$SRC_ARG" ]; then
  SRC="$(cd "$SRC_ARG" && pwd)"
fi

MG="$ROOT/data/metagenome"; S16="$ROOT/data/16s"; REF="$ROOT/data/reference"
CFG="$ROOT/config"
mkdir -p "$MG" "$S16" "$REF" "$CFG"

PROJECT="PRJNA627197"
KEBJ="https://sra-download.ncbi.nlm.nih.gov/traces/wgs01/wgs_aux/KE/BJ/KEBJ01"
SILVA_URL="https://mothur.s3.us-east-2.amazonaws.com/wiki/silva.nr_v132.tgz"
ENA="https://www.ebi.ac.uk/ena/portal/api/filereport"

c_hd(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
c_ok(){ printf '   \033[32m✓\033[0m %s\n' "$*"; }
c_mv(){ printf '   \033[36m→\033[0m %s\n' "$*"; }
c_dl(){ printf '   \033[35m↓\033[0m %s\n' "$*"; }
c_no(){ printf '   \033[33m•\033[0m %s\n' "$*"; }
c_er(){ printf '   \033[31m✗\033[0m %s\n' "$*"; }

# canonical metagenome samples
MG_SAMPLES="ARS BQF BQS BR1F BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETS FAS MTF \
PBS PFF PFS PGF PGS PLS QH2F QHS1 QHS2 QNF QNS RSF RSS RVF SIF SIS SLF SLS TCF TCS"

# a file is "valid" if it exists, is non-empty, and (for .gz) is a real gzip
valid() {
  local f="$1"
  [ -f "$f" ] || return 1
  [ -s "$f" ] || return 1
  case "$f" in
    *.gz) gzip -t "$f" 2>/dev/null || return 1 ;;
  esac
  return 0
}

# find a sample read in SRC under any naming (<S>_R1 / <S>_MG_R1 / <S><date>_MG_R1)
find_src() {
  local sample="$1" read="$2"
  [ -z "$SRC" ] && return 1
  local cand
  for pat in "${sample}_${read}.fastq.gz" "${sample}_MG_${read}.fastq.gz" \
             "${sample}"*"_MG_${read}.fastq.gz"; do
    cand=$(ls "$SRC"/$pat 2>/dev/null | head -1 || true)
    [ -n "$cand" ] && { echo "$cand"; return 0; }
  done
  return 1
}

place() {   # src dst : move (or copy) a real file into place
  local src="$1" dst="$2"
  [ "$CHECK_ONLY" = "1" ] && return 0
  $MODE_MOVE -f "$src" "$dst"
}

# =============================================================================
# 1. METAGENOME READS
# =============================================================================
do_reads() {
  c_hd "Metagenome reads (35 samples)"
  local ok=0 moved=0 missing=""
  for s in $MG_SAMPLES; do
    local d1="$MG/${s}_R1.fastq.gz" d2="$MG/${s}_R2.fastq.gz"
    if valid "$d1" && valid "$d2"; then c_ok "$s"; ok=$((ok+1)); continue; fi
    # try the source folder
    local f1 f2
    f1=$(find_src "$s" R1 || true); f2=$(find_src "$s" R2 || true)
    if [ -n "$f1" ] && [ -n "$f2" ]; then
      place "$f1" "$d1"; place "$f2" "$d2"
      c_mv "$s (from $(basename "$f1"))"; moved=$((moved+1)); continue
    fi
    missing="$missing $s"
  done
  echo "   ---"; c_ok "$ok in place, $moved from source"
  if [ -n "$missing" ]; then
    c_no "missing:$missing"
    [ "$CHECK_ONLY" = "1" ] && return
    download_reads "$missing"
  fi
}

download_reads() {
  local want="$1"
  c_hd "Downloading missing reads from ENA"
  if [ ! -f "$REF/ena_map.tsv" ]; then
    curl -fSL --retry 3 -o "$REF/ena_raw.tsv" \
      "${ENA}?accession=${PROJECT}&result=read_run&format=tsv&fields=run_accession,library_name,fastq_ftp" || {
      c_er "could not reach ENA"; return 1; }
    python3 - "$REF/ena_raw.tsv" "$REF/ena_map.tsv" <<'PY'
import sys,re,csv
raw,out=sys.argv[1],sys.argv[2]
K=set("ARS BQF BQS BQS1 BR1F BRF1 BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETF ETS FAF FAS MTF PBS PFF PFS PGF PGS PLS QHF2 QH2F QHS1 QHS2 QNF QNS RSF RSS RVF SIF SIS SLF SLS STS TCF TCS VCS".split())
def code(l):
    fi=l.split('_')[0];m=re.match(r'^(.*?)(\d{6})$',fi);h=m.group(1) if m else fi
    return h if h in K else (fi if fi in K else next((k for k in sorted(K,key=len,reverse=True) if l.startswith(k)), h))
w=csv.writer(open(out,"w"),delimiter="\t");w.writerow(["s","run","ftp"])
r=csv.reader(open(raw),delimiter="\t");next(r,None)
[w.writerow([code(x[1]),x[0],x[2]]) for x in r if len(x)>=3]
PY
  fi
  for s in $want; do
    local line; line=$(grep -P "^${s}\t" "$REF/ena_map.tsv" | head -1 || true)
    [ -z "$line" ] && { c_er "$s: not in ENA"; continue; }
    local ftp r1 r2; ftp=$(echo "$line"|cut -f3)
    r1=$(echo "$ftp"|cut -d';' -f1); r2=$(echo "$ftp"|cut -d';' -f2)
    [ -z "$r1" ] && { c_er "$s: no fastq"; continue; }
    c_dl "$s"
    curl -fSL --retry 3 -o "$MG/${s}_R1.fastq.gz" "https://$r1"
    curl -fSL --retry 3 -o "$MG/${s}_R2.fastq.gz" "https://$r2"
  done
}

# =============================================================================
# 2. 16S PROCESSED SEQUENCES (KEBJ01)
# =============================================================================
do_16s() {
  c_hd "16S processed sequences (KEBJ01)"
  local dst="$S16/kebj01_16s.fasta"
  if valid "$dst"; then c_ok "kebj01_16s.fasta ($(grep -c '^>' "$dst") seqs)"; return; fi
  # in source?
  if [ -n "$SRC" ] && valid "$SRC/kebj01_16s.fasta"; then
    place "$SRC/kebj01_16s.fasta" "$dst"; c_mv "kebj01_16s.fasta (from source)"; return
  fi
  c_no "not present"
  [ "$CHECK_ONLY" = "1" ] && return
  c_dl "downloading KEBJ01 from NCBI (~77 MB)"
  for i in 1 2 3; do curl -fSL --retry 3 -o "$S16/K.$i.gz" "$KEBJ/KEBJ01.$i.fsa_nt.gz"; done
  gunzip -c "$S16"/K.*.gz > "$dst"; rm -f "$S16"/K.*.gz
  valid "$dst" && c_ok "kebj01_16s.fasta ($(grep -c '^>' "$dst") seqs)" || c_er "KEBJ download failed"
}

# =============================================================================
# 3. SILVA REFERENCE  (always fresh, verified)
# =============================================================================
do_silva() {
  c_hd "SILVA v132 reference (fresh download, verified)"
  if [ "$CHECK_ONLY" = "1" ]; then c_no "would download SILVA (~350 MB)"; return; fi
  c_dl "downloading SILVA v132 from mothur"
  curl -fSL --retry 3 -o "$REF/silva.tgz" "$SILVA_URL" || { c_er "SILVA download failed"; return 1; }
  gzip -t "$REF/silva.tgz" 2>/dev/null || { c_er "SILVA archive corrupt"; rm -f "$REF/silva.tgz"; return 1; }
  tar -xzf "$REF/silva.tgz" -C "$REF" 2>/dev/null
  mv -f "$REF"/silva.nr_v132.align "$REF/silva_v132.db"
  mv -f "$REF"/silva.nr_v132.tax   "$REF/silva_v132.tax"
  rm -f "$REF/silva.tgz"
  valid "$REF/silva_v132.db" && c_ok "silva_v132.db ($(grep -c '^>' "$REF/silva_v132.db") seqs) + .tax" \
    || c_er "SILVA extract failed"
}

# =============================================================================
# 4. REFERENCE TABLES  (env + params; bundled or from source)
# =============================================================================
do_tables() {
  c_hd "Reference tables"
  # bundled with the project (must exist)
  for f in ec_carbon.csv geochem_by_station.csv cell_counts_by_station.csv; do
    valid "$REF/$f" && c_ok "$f (bundled)" || c_er "$f MISSING from project — re-add it"
  done
  # geochem.csv / cell_counts.csv : from source, else build from station tables
  for f in geochem.csv cell_counts.csv; do
    if valid "$REF/$f"; then c_ok "$f"; continue; fi
    if [ -n "$SRC" ] && valid "$SRC/$f"; then place "$SRC/$f" "$REF/$f"; c_mv "$f (from source)"
    else c_no "$f will be built from station tables"; fi
  done
  # flux_params.yml -> config/
  if valid "$CFG/flux_params.yml"; then c_ok "flux_params.yml"
  elif [ -n "$SRC" ] && valid "$SRC/flux_params.yml"; then place "$SRC/flux_params.yml" "$CFG/flux_params.yml"; c_mv "flux_params.yml (from source)"
  else c_no "flux_params.yml missing"; fi
  # build sample-indexed env tables if needed
  if [ "$CHECK_ONLY" = "0" ] && { [ ! -f "$REF/geochem.csv" ] || [ ! -f "$REF/cell_counts.csv" ]; }; then
    build_env
  fi
}

build_env() {
  [ -f "$REF/geochem_by_station.csv" ] || return 0
  [ -f "$CFG/sample_station_map.tsv" ] || return 0
  python3 - "$CFG/sample_station_map.tsv" "$REF/geochem_by_station.csv" \
             "$REF/cell_counts_by_station.csv" "$REF/geochem.csv" "$REF/cell_counts.csv" <<'PY'
import sys,csv
mapf,geof,cellf,go,co=sys.argv[1:6]
sm={r["sample"]:r["station"] for r in csv.DictReader(open(mapf),delimiter="\t")}
def load(p):
    r=csv.DictReader(open(p));return r.fieldnames,{x["station"]:x for x in r}
gc,geo=load(geof);cc,cell=load(cellf)
with open(go,"w",newline="") as f:
    w=csv.writer(f);w.writerow(["sample"]+[c for c in gc if c!="station"])
    for s,st in sm.items():
        if st in geo: w.writerow([s]+[geo[st][c] for c in gc if c!="station"])
with open(co,"w",newline="") as f:
    w=csv.writer(f);w.writerow(["sample"]+[c for c in cc if c!="station"])
    for s,st in sm.items():
        if st in cell: w.writerow([s]+[cell[st][c] for c in cc if c!="station"])
print("   built geochem.csv + cell_counts.csv (sample-indexed)")
PY
  c_ok "built sample-indexed env tables"
}

# =============================================================================
# FINAL VERIFICATION
# =============================================================================
verify() {
  c_hd "Final check"
  local fail=0
  local n1; n1=$(ls "$MG"/*_R1.fastq.gz 2>/dev/null | wc -l)
  [ "$n1" -ge 35 ] && c_ok "metagenome reads: $n1/35" || { c_er "metagenome reads: $n1/35"; fail=1; }
  valid "$S16/kebj01_16s.fasta" && c_ok "16S sequences" || { c_er "16S sequences MISSING"; fail=1; }
  valid "$REF/silva_v132.db"    && c_ok "SILVA"         || { c_er "SILVA MISSING"; fail=1; }
  valid "$REF/ec_carbon.csv"    && c_ok "ec_carbon.csv" || { c_er "ec_carbon.csv MISSING"; fail=1; }
  valid "$REF/geochem.csv"      && c_ok "geochem.csv"   || c_no "geochem.csv (optional per-sample)"
  # spot-check one read is actually readable (catches broken files)
  local probe; probe=$(ls "$MG"/*_R1.fastq.gz 2>/dev/null | head -1)
  if [ -n "$probe" ]; then
    # valid gzip + a non-empty first line = readable. (avoid SIGPIPE false alarms)
    if gzip -t "$probe" 2>/dev/null && [ -n "$(zcat "$probe" 2>/dev/null | head -c 1)" ]; then
      c_ok "reads are readable (spot-check $(basename "$probe" _R1.fastq.gz))"
    else
      c_er "reads not readable!"; fail=1
    fi
  fi
  echo
  if [ "$fail" = "0" ]; then
    printf '\033[1;32m✓ ALL DATA READY.\033[0m  next:  python3 workflow/end_to_end.py\n'
  else
    printf '\033[1;31m✗ Some data missing — see above.\033[0m\n'; return 1
  fi
}

# =============================================================================
# run
# =============================================================================
[ -n "$SRC" ] && c_hd "Source: $SRC   (mode: $MODE_MOVE)" || c_hd "No source — will download everything"
[ "$CHECK_ONLY" = "1" ] && c_hd "CHECK-ONLY (no changes)"

do_reads
do_16s
do_silva
do_tables
verify
