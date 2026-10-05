#!/usr/bin/env bash
# =============================================================================
# get_data.sh  —  fetch & organize EVERY input for the SubductCR workflow
# =============================================================================
# Pulls from all sources and lays everything out under data/, ready to run:
#
#   NCBI   KEBJ01            -> data/16s/kebj01_16s.fasta   (processed 16S)
#   mothur SILVA v132        -> data/reference/silva_v132.* (16S reference)
#   ENA    PRJNA627197       -> data/metagenome/*.fastq.gz  (metagenome reads)
#   GitHub dgiovannelli repo -> data/reference/ (authors' deposited 16S tables)
#   (bundled) Suppl. Tables  -> data/reference/ (geochem, cell counts, EC list)
#
# Sample codes are taken from each ENA library Name (e.g. TCF170221 -> TCF),
# which matches the station codes in the paper.
#
# Usage:  ./bin/get_data.sh [all|16s|silva|reads|github|geochem|check]
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S16="$ROOT/data/16s"; MG="$ROOT/data/metagenome"; REF="$ROOT/data/reference"
CFG="$ROOT/config"
mkdir -p "$S16" "$MG" "$REF"

PROJECT="PRJNA627197"
KEBJ="https://sra-download.ncbi.nlm.nih.gov/traces/wgs01/wgs_aux/KE/BJ/KEBJ01"
SILVA="https://mothur.s3.us-east-2.amazonaws.com/wiki/silva.nr_v132.tgz"
ENA="https://www.ebi.ac.uk/ena/portal/api/filereport"
GH="https://raw.githubusercontent.com/dgiovannelli/SubductCR_16S-diversity/master"

log(){ printf '\n\033[1;34m== %s\033[0m\n' "$*"; }
ok(){ printf '   \033[32m✓\033[0m %s\n' "$*"; }
note(){ printf '   \033[33m•\033[0m %s\n' "$*"; }

# -----------------------------------------------------------------------------
get_16s() {
  log "16S processed sequences  (NCBI KEBJ01)"
  if [ -f "$S16/kebj01_16s.fasta" ]; then ok "already present"; return; fi
  for i in 1 2 3; do
    note "part $i/3"; curl -fSL --retry 3 -o "$S16/KEBJ01.$i.fsa_nt.gz" "$KEBJ/KEBJ01.$i.fsa_nt.gz"
  done
  gunzip -c "$S16"/KEBJ01.*.fsa_nt.gz > "$S16/kebj01_16s.fasta"
  rm -f "$S16"/KEBJ01.*.fsa_nt.gz
  ok "kebj01_16s.fasta ($(grep -c '^>' "$S16/kebj01_16s.fasta") sequences)"
}

get_silva() {
  log "SILVA v132 reference  (mothur)"
  if [ -f "$REF/silva_v132.db" ]; then ok "already present"; return; fi
  note "downloading (~600 MB)"; curl -fSL --retry 3 -o "$REF/silva.tgz" "$SILVA"
  tar -xzf "$REF/silva.tgz" -C "$REF"
  mv "$REF"/silva.nr_v132.align "$REF/silva_v132.db"
  mv "$REF"/silva.nr_v132.tax   "$REF/silva_v132.tax"
  rm -f "$REF/silva.tgz"
  ok "silva_v132.db + silva_v132.tax"
}

get_github() {
  log "Authors' deposited 16S tables  (GitHub)"
  # the reproduce path can use these directly; also handy for validation
  for f in 16S_rRNA_data/bac_normalized_count.csv \
           16S_rRNA_data/bac_taxonomy.csv \
           16S_rRNA_data/bac_tree.tre \
           16S_rRNA_data/bac_sample_table.csv ; do
    out="$REF/$(basename "$f")"
    if [ -f "$out" ]; then ok "$(basename "$f") present"; continue; fi
    if curl -fSL --retry 3 -o "$out" "$GH/$f" 2>/dev/null; then ok "$(basename "$f")"
    else note "$(basename "$f") not fetched (repo path may differ)"; fi
  done
}

build_map() {
  log "Sample map from ENA ($PROJECT)"
  curl -fSL --retry 3 -o "$REF/ena_raw.tsv" \
    "${ENA}?accession=${PROJECT}&result=read_run&format=tsv&fields=run_accession,library_name,fastq_ftp"
  python3 - "$REF/ena_raw.tsv" "$REF/ena_map.tsv" <<'PY'
import sys, re, csv
raw, out = sys.argv[1], sys.argv[2]
KNOWN = set("""ARS BQF BQS BQS1 BR1F BRF1 BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9
ETF ETS FAF FAS MTF PBS PFF PFS PGF PGS PLS QHF2 QH2F QHS1 QHS2 QNF QNS
RSF RSS RVF SIF SIS SLF SLS STS TCF TCS VCS""".split())
def code(lib):
    first=lib.split('_')[0]; m=re.match(r'^(.*?)(\d{6})$',first)
    head=m.group(1) if m else first
    if head in KNOWN: return head
    if first in KNOWN: return first
    for k in sorted(KNOWN,key=len,reverse=True):
        if lib.startswith(k): return k
    return head or lib
with open(raw) as fi, open(out,"w",newline="") as fo:
    r=csv.reader(fi,delimiter="\t"); w=csv.writer(fo,delimiter="\t"); next(r,None)
    w.writerow(["sample","run_accession","fastq_ftp"])
    for row in r:
        if len(row)<3: continue
        w.writerow([code(row[1]), row[0], row[2]])
PY
  ok "ena_map.tsv ($(($(wc -l < "$REF/ena_map.tsv")-1)) libraries)"
}

get_reads() {
  [ -f "$REF/ena_map.tsv" ] || build_map
  log "Metagenome reads  (ENA $PROJECT)"
  tail -n +2 "$REF/ena_map.tsv" | while IFS=$'\t' read -r s run ftp; do
    [ -z "$s" ] && continue
    [ -f "$MG/${s}_R1.fastq.gz" ] && [ -f "$MG/${s}_R2.fastq.gz" ] && { ok "$s present"; continue; }
    r1=$(echo "$ftp"|cut -d';' -f1); r2=$(echo "$ftp"|cut -d';' -f2)
    [ -z "$r1" ] && { note "$s: no fastq listed"; continue; }
    note "$s ($run)"
    curl -fSL --retry 3 -o "$MG/${s}_R1.fastq.gz" "https://$r1"
    curl -fSL --retry 3 -o "$MG/${s}_R2.fastq.gz" "https://$r2"
    ok "$s"
  done
}

build_geochem() {
  log "Building sample-indexed environmental tables"
  # join station-level geochem + cell counts onto each sample via the map
  python3 - "$CFG/sample_station_map.tsv" \
             "$REF/geochem_by_station.csv" \
             "$REF/cell_counts_by_station.csv" \
             "$REF/geochem.csv" "$REF/cell_counts.csv" <<'PY'
import sys, csv
mapf, geof, cellf, geo_out, cell_out = sys.argv[1:6]
# sample -> station
smap = {}
with open(mapf) as f:
    r=csv.DictReader(f,delimiter="\t")
    for row in r: smap[row["sample"]] = row["station"]
def load(path,key="station"):
    d={}
    with open(path) as f:
        r=csv.DictReader(f)
        for row in r: d[row[key]] = row
    return r.fieldnames, d
gcols, geo = load(geof)
ccols, cell = load(cellf)
# write geochem.csv indexed by sample
with open(geo_out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["sample"]+[c for c in gcols if c!="station"])
    miss=[]
    for s,st in smap.items():
        if st in geo: w.writerow([s]+[geo[st][c] for c in gcols if c!="station"])
        else: miss.append(s)
    if miss: sys.stderr.write("  no geochem for: %s\n" % " ".join(miss))
with open(cell_out,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["sample"]+[c for c in ccols if c!="station"])
    for s,st in smap.items():
        if st in cell: w.writerow([s]+[cell[st][c] for c in ccols if c!="station"])
print("  wrote geochem.csv + cell_counts.csv (sample-indexed)")
PY
  ok "geochem.csv + cell_counts.csv"
}

check() {
  log "Final inventory"
  for f in "$S16/kebj01_16s.fasta" "$REF/silva_v132.db" "$REF/silva_v132.tax" \
           "$REF/geochem.csv" "$REF/cell_counts.csv" "$REF/ec_carbon.csv"; do
    [ -f "$f" ] && ok "$(basename "$f")" || note "MISSING $(basename "$f")"
  done
  n=$(ls "$MG"/*_R1.fastq.gz 2>/dev/null | wc -l)
  ok "$n metagenome read pairs in data/metagenome/"
}

case "${1:-all}" in
  16s)     get_16s ;;
  silva)   get_silva ;;
  github)  get_github ;;
  reads)   get_reads ;;
  geochem) build_geochem ;;
  check)   check ;;
  all)     get_16s; get_silva; get_github; build_map; get_reads
           build_geochem; check
           log "All data fetched and organized under data/." ;;
  *) echo "usage: $0 [all|16s|silva|github|reads|geochem|check]"; exit 1 ;;
esac
