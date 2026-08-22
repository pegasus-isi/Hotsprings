#!/usr/bin/env bash
# =====================================================================
# fetch_inputs.sh  -- download & stage every input the workflow needs.
#
# Fills input/ with:
#   silva_v132.db (+ .tax)   SILVA v132 reference for mothur classify.seqs
#   (GS+ DB is built into the mi-faser container -- not downloaded)
#   geochem.csv              from reference_data/ (already in repo)
#   cell_counts.csv          template scaffolded from reference_data/cell_ct.Rmd
#   <SAMPLE>_16S_R{1,2}.fastq.gz   16S reads  (SRA BioProject PRJNA579365)
#   <SAMPLE>_MG_R{1,2}.fastq.gz    metagenomes(SRA BioProject PRJNA627197)
#
# Usage (run from the project root):
#   ./fetch_inputs.sh                 # everything
#   ./fetch_inputs.sh --skip-reads    # skip the big SRA downloads
#   ./fetch_inputs.sh --only silva    # one of: silva|gsplus|tables|reads
#   ./fetch_inputs.sh --threads 8
#   ./fetch_inputs.sh --no-install   # do not auto-install sra-tools/edirect
#
# Prereqs (install/module-load first):
#   wget or curl, tar        (reads are pulled from ENA over HTTPS)

# =====================================================================
set -euo pipefail

THREADS=4
DO_SILVA=1; DO_GSPLUS=1; DO_TABLES=1; DO_READS=1; DO_INSTALL=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --threads) THREADS="$2"; shift 2;;
    --skip-reads) DO_READS=0; shift;;
    --skip-silva) DO_SILVA=0; shift;;
    --skip-gsplus) DO_GSPLUS=0; shift;;
    --no-install) DO_INSTALL=0; shift;;
    --only) DO_SILVA=0; DO_GSPLUS=0; DO_TABLES=0; DO_READS=0
            case "$2" in
              silva) DO_SILVA=1;; gsplus) DO_GSPLUS=1;;
              tables) DO_TABLES=1;; reads) DO_READS=1;;
              *) echo "unknown --only target: $2"; exit 1;;
            esac; shift 2;;
    *) echo "unknown option: $1"; exit 1;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IN="$ROOT/input"; REF="$ROOT/reference_data"
mkdir -p "$IN"
cd "$ROOT"

SILVA_URL="https://mothur.s3.us-east-2.amazonaws.com/wiki/silva.nr_v132.tgz"
BP_16S="PRJNA579365"
BP_MG="PRJNA627197"
SAMPLES=(ES RS SM SR SI MT BQ VC BR CY SL QN TC RV ET QH EP HN)

have(){ command -v "$1" >/dev/null 2>&1; }
dl(){ # dl URL OUTFILE
  if have wget; then wget -c -O "$2" "$1";
  elif have curl; then curl -L -C - -o "$2" "$1";
  else echo "ERROR: need wget or curl"; exit 1; fi
}

TOOLS="$ROOT/tools"          # self-contained tool install dir
ENVSH="$TOOLS/env.sh"        # source this to get the tools on PATH later
mkdir -p "$TOOLS"

persist_path(){ # persist_path DIR  -> append to tools/env.sh once
  local d="$1"
  touch "$ENVSH"
  grep -qsF "$d" "$ENVSH" || echo "export PATH=\"$d:\$PATH\"" >> "$ENVSH"
  export PATH="$d:$PATH"
}

install_sra_tools(){
  have prefetch && have fasterq-dump && return 0
  echo "    installing SRA Toolkit into $TOOLS ..."
  local os plat
  os="$(uname -s)"
  case "$os" in
    Linux)  plat="sratoolkit.current-centos_linux64" ;;
    Darwin) plat="sratoolkit.current-mac64" ;;
    *) echo "    ERROR: unsupported OS $os for auto-install"; return 1 ;;
  esac
  local url="https://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/current/${plat}.tar.gz"
  local tgz="$TOOLS/${plat}.tar.gz"
  dl "$url" "$tgz"
  tar xzf "$tgz" -C "$TOOLS"
  local bin; bin="$(ls -d "$TOOLS"/sratoolkit.*/bin 2>/dev/null | head -1)"
  [[ -n "$bin" ]] || { echo "    ERROR: sra-tools bin not found after extract"; return 1; }
  persist_path "$bin"
  # non-interactive config; cache under scratch-friendly tools dir
  mkdir -p "$TOOLS/ncbi"
  vdb-config --set "/repository/user/main/public/root=$TOOLS/ncbi" >/dev/null 2>&1 || true
  vdb-config --set "/repository/user/cache-disabled=false" >/dev/null 2>&1 || true
  have prefetch && echo "    sra-tools OK ($(prefetch --version 2>/dev/null | head -1))"
}

install_edirect(){
  have esearch && have efetch && return 0
  echo "    installing EDirect into $HOME/edirect ..."
  if have wget; then
    sh -c "$(wget -q https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh -O -)" </dev/null >/dev/null 2>&1 || true
  elif have curl; then
    sh -c "$(curl -fsSL https://ftp.ncbi.nlm.nih.gov/entrez/entrezdirect/install-edirect.sh)" </dev/null >/dev/null 2>&1 || true
  fi
  [[ -d "$HOME/edirect" ]] && persist_path "$HOME/edirect"
  have esearch && echo "    edirect OK" || echo "    WARN: edirect install may have failed"
}

ensure_read_tools(){
  # Reads are fetched from ENA over HTTPS -- only wget/curl needed.
  have wget || have curl || { echo "ERROR: need wget or curl for reads"; exit 1; }
}

# ---------------------------------------------------------------------
# 1. SILVA v132 reference (align + taxonomy) for mothur
# ---------------------------------------------------------------------
if [[ $DO_SILVA -eq 1 ]]; then
  echo "==> [silva] SILVA v132 reference"
  if [[ -f "$IN/silva_v132.db" && -f "$IN/silva_v132.tax" ]]; then
    echo "    already present, skipping"
  else
    TGZ="$IN/silva.nr_v132.tgz"
    [[ -f "$TGZ" ]] || dl "$SILVA_URL" "$TGZ"
    tar xzf "$TGZ" -C "$IN"
    # mothur release ships silva.nr_v132.align + silva.nr_v132.tax
    cp "$IN/silva.nr_v132.align" "$IN/silva_v132.db"
    cp "$IN/silva.nr_v132.tax"   "$IN/silva_v132.tax"
    echo "    staged silva_v132.db (+ .tax)"
    echo "    NOTE: paper used a VAMPS-trimmed variant (silva.nr_v132_vamps);"
    echo "          the standard mothur v132 above is the public equivalent."
  fi
fi

# ---------------------------------------------------------------------
# 2. mi-faser GS+ DB -- built into the container; nothing to download
# ---------------------------------------------------------------------
if [[ $DO_GSPLUS -eq 1 ]]; then
  echo "==> [gsplus] built into the mi-faser container (bin/mifaser uses -d GS+)"
  echo "    nothing to download; gsplus.db is no longer a workflow input"
fi

# ---------------------------------------------------------------------
# 3. Small tables (already in the repo)
# ---------------------------------------------------------------------
if [[ $DO_TABLES -eq 1 ]]; then
  echo "==> [tables] geochem.csv + cell_counts.csv"
  if [[ -f "$REF/geochem.csv" ]]; then
    cp "$REF/geochem.csv" "$IN/geochem.csv"; echo "    staged geochem.csv"
  else
    echo "    WARN: reference_data/geochem.csv missing"
  fi
  if [[ ! -f "$IN/cell_counts.csv" ]]; then
    # scaffold a template; fill densities from reference_data/cell_ct.Rmd
    { echo "sample,cells_per_ml"
      for s in "${SAMPLES[@]}"; do echo "$s,"; done
    } > "$IN/cell_counts.csv"
    echo "    wrote cell_counts.csv TEMPLATE (fill values from cell_ct.Rmd)"
  fi
fi

# ---------------------------------------------------------------------
# 4. Raw reads from SRA
# ---------------------------------------------------------------------
# ENA gives direct fastq.gz URLs + a run table in one HTTPS call (no sra-tools,
# no edirect, no Perl). We map each run to a sample code using the authoritative
# sample table shipped in the repo (reference_data/geochem.csv: sample,code,station).
map_code(){ # lib alias  -> best-guess sample code
  local lib="$1" alias="$2" t="$REF/geochem.csv" code=""
  if [[ -f "$t" ]]; then
    # match the run's library/alias against the station column (col 3)
    code=$(awk -F, -v L="$lib" -v A="$alias" 'NR>1 && $3!="" { if (index(L,$3)||index(A,$3)) {print $2; exit} }' "$t")
    # else against the 2-letter code column (col 2)
    [[ -z "$code" ]] && code=$(awk -F, -v L="$lib" -v A="$alias" 'NR>1 && $2!="" { if (index(L,$2)||index(A,$2)) {print $2; exit} }' "$t")
  fi
  [[ -z "$code" ]] && code="$(echo "${lib:-$alias}" | tr -c 'A-Za-z0-9' '_' | sed 's/_*$//')"
  echo "$code"
}

fetch_project(){ # fetch_project BIOPROJECT SUFFIX(16S|MG)
  local bp="$1" suffix="$2"
  echo "==> [reads/$suffix] BioProject $bp (via ENA)"
  local tsv="$IN/ena_${suffix}.tsv"
  local url="https://www.ebi.ac.uk/ena/portal/api/filereport?accession=${bp}&result=read_run&fields=run_accession,library_name,sample_alias,fastq_ftp&format=tsv&limit=0"
  dl "$url" "$tsv"
  local n; n=$(($(wc -l < "$tsv")-1))
  echo "    $n runs listed"
  # cols: run_accession(1) library_name(2) sample_alias(3) fastq_ftp(4)
  tail -n +2 "$tsv" | while IFS=$'\t' read -r run lib alias ftp; do
    [[ -z "$run" ]] && continue
    if [[ -z "$ftp" ]]; then echo "    $run: no fastq_ftp on ENA yet, skip"; continue; fi
    local code; code="$(map_code "$lib" "$alias")"
    local r1u="${ftp%%;*}" r2u="${ftp##*;}"
    local out1="$IN/${code}_${suffix}_R1.fastq.gz" out2="$IN/${code}_${suffix}_R2.fastq.gz"
    if [[ -f "$out1" && -f "$out2" ]]; then echo "    $code ($run) present, skip"; continue; fi
    echo "    $run -> ${code}   (lib='$lib' alias='$alias')"
    dl "https://$r1u" "$out1"
    if [[ "$r2u" != "$r1u" ]]; then dl "https://$r2u" "$out2"; else echo "      note: single-end run, no R2"; fi
  done
  echo "    mapping written to $tsv  (verify code assignments before running!)"
}

if [[ $DO_READS -eq 1 ]]; then
  ensure_read_tools
  fetch_project "$BP_16S" "16S"
  fetch_project "$BP_MG"  "MG"
  echo "    NOTE: run->code mapping is heuristic (matched against the repo sample"
  echo "          table). Spot-check ena_16S.tsv / ena_MG.tsv and rename if needed."
fi

# ---------------------------------------------------------------------
# 5. Status
# ---------------------------------------------------------------------
echo; echo "==> input/ status"
for f in silva_v132.db geochem.csv cell_counts.csv flux_params.yml; do
  [[ -e "$IN/$f" ]] && echo "   OK       $f" || echo "   MISSING  $f"
done
echo "   16S read pairs: $(ls "$IN"/*_16S_R1.fastq.gz 2>/dev/null | wc -l) / 18"
echo "   MG  read pairs: $(ls "$IN"/*_MG_R1.fastq.gz  2>/dev/null | wc -l) / 10"
echo "Done."
