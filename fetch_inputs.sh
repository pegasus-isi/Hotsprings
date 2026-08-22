#!/usr/bin/env bash
# =====================================================================
# fetch_inputs.sh  -- download & stage every input the workflow needs.
#
# Fills input/ with:
#   silva_v132.db (+ .tax)   SILVA v132 reference for mothur classify.seqs
#   gsplus.db                mi-faser Gold-Standard-Plus DB (from the container)
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
#
# Prereqs (install/module-load first):
#   wget or curl, tar
#   sra-tools  (prefetch, fasterq-dump)   -- for --reads
#   entrez-direct (esearch, efetch)       -- to resolve run accessions
#   docker OR singularity/apptainer       -- to extract the GS+ DB
# =====================================================================
set -euo pipefail

THREADS=4
DO_SILVA=1; DO_GSPLUS=1; DO_TABLES=1; DO_READS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --threads) THREADS="$2"; shift 2;;
    --skip-reads) DO_READS=0; shift;;
    --skip-silva) DO_SILVA=0; shift;;
    --skip-gsplus) DO_GSPLUS=0; shift;;
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
# 2. mi-faser Gold-Standard-Plus DB (extract from the container)
# ---------------------------------------------------------------------
if [[ $DO_GSPLUS -eq 1 ]]; then
  echo "==> [gsplus] mi-faser GS+ database"
  if [[ -e "$IN/gsplus.db" ]]; then
    echo "    already present, skipping"
  elif have docker; then
    cid="$(docker create bromberglab/mifaser:latest)"
    # GS+ ships inside the image under the mifaser package 'database' dir
    docker cp "$cid:/mifaser/database" "$IN/gsplus.db" 2>/dev/null \
      || docker cp "$cid:/usr/local/lib/python3/dist-packages/mifaser/database" "$IN/gsplus.db" 2>/dev/null \
      || echo "    WARN: could not locate DB path inside image; see note below"
    docker rm "$cid" >/dev/null
    [[ -e "$IN/gsplus.db" ]] && echo "    extracted gsplus.db from container"
  elif have singularity || have apptainer; then
    SING=$(command -v singularity || command -v apptainer)
    SIF="$ROOT/containers/sif/subductcr-mifaser.sif"
    [[ -f "$SIF" ]] || SIF="docker://bromberglab/mifaser:latest"
    "$SING" exec "$SIF" bash -c 'cp -r $(python3 -c "import mifaser,os;print(os.path.join(os.path.dirname(mifaser.__file__),\"database\"))") /tmp/gsplusdb' \
      && "$SING" exec "$SIF" cp -r /tmp/gsplusdb "$IN/gsplus.db" 2>/dev/null \
      || echo "    WARN: extraction via singularity failed; see note below"
  else
    echo "    WARN: no docker/singularity to extract GS+."
  fi
  if [[ ! -e "$IN/gsplus.db" ]]; then
    cat <<'EOF'
    NOTE: GS+ is bundled inside the mi-faser container. If extraction failed,
    the simplest fix is to have the mifaser job use the built-in DB name
    instead of a staged file: edit bin/mifaser to call `mifaser ... -d GS+`
    and remove gsplus.db from the replica catalog in subductcr_workflow.py.
EOF
  fi
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
fetch_project(){ # fetch_project BIOPROJECT SUFFIX(16S|MG)
  local bp="$1" suffix="$2"
  echo "==> [reads/$suffix] BioProject $bp"
  local runinfo="$IN/runinfo_${suffix}.csv"
  if [[ ! -f "$runinfo" ]]; then
    have esearch && have efetch || { echo "    ERROR: entrez-direct (esearch/efetch) required to resolve $bp"; return 1; }
    esearch -db sra -query "$bp" | efetch -format runinfo > "$runinfo"
  fi
  # columns: Run(1) ... LibraryName ... SampleName ; find them by header
  local hdr; hdr="$(head -1 "$runinfo")"
  local ci_run ci_lib ci_smp
  ci_run=$(awk -F, -v h="$hdr" 'BEGIN{n=split(h,a,",");for(i=1;i<=n;i++)if(a[i]=="Run")print i}')
  ci_lib=$(awk -F, -v h="$hdr" 'BEGIN{n=split(h,a,",");for(i=1;i<=n;i++)if(a[i]=="LibraryName")print i}')
  ci_smp=$(awk -F, -v h="$hdr" 'BEGIN{n=split(h,a,",");for(i=1;i<=n;i++)if(a[i]=="SampleName")print i}')

  tail -n +2 "$runinfo" | while IFS=, read -r -a f; do
    local run="${f[$((ci_run-1))]}"
    local lib="${f[$((ci_lib-1))]:-}" smp="${f[$((ci_smp-1))]:-}"
    [[ -z "$run" ]] && continue
    # map to one of our sample codes by matching lib/sample text
    local code=""
    for s in "${SAMPLES[@]}"; do
      if [[ "$lib" == *"$s"* || "$smp" == *"$s"* ]]; then code="$s"; break; fi
    done
    if [[ -z "$code" ]]; then
      echo "    ? run $run: no sample-code match (lib='$lib' smp='$smp') -> using $run"
      code="$run"
    fi
    local out1="$IN/${code}_${suffix}_R1.fastq.gz" out2="$IN/${code}_${suffix}_R2.fastq.gz"
    if [[ -f "$out1" && -f "$out2" ]]; then echo "    $code ($run) present, skip"; continue; fi
    echo "    downloading $run -> $code"
    prefetch "$run" -O "$IN/sra" >/dev/null
    fasterq-dump "$IN/sra/$run/$run.sra" -O "$IN/sra" --split-files -e "$THREADS" >/dev/null
    gzip -c "$IN/sra/${run}_1.fastq" > "$out1"
    gzip -c "$IN/sra/${run}_2.fastq" > "$out2"
    rm -f "$IN/sra/${run}"_*.fastq
  done
}

if [[ $DO_READS -eq 1 ]]; then
  have prefetch && have fasterq-dump || { echo "ERROR: sra-tools (prefetch, fasterq-dump) required for --reads"; exit 1; }
  fetch_project "$BP_16S" "16S"
  fetch_project "$BP_MG"  "MG"
  echo "    NOTE: verify the SRA->sample mapping above; SRA metadata field names"
  echo "          vary, so spot-check that codes (ES,RS,...) matched correctly."
fi

# ---------------------------------------------------------------------
# 5. Status
# ---------------------------------------------------------------------
echo; echo "==> input/ status"
for f in silva_v132.db gsplus.db geochem.csv cell_counts.csv flux_params.yml; do
  [[ -e "$IN/$f" ]] && echo "   OK       $f" || echo "   MISSING  $f"
done
echo "   16S read pairs: $(ls "$IN"/*_16S_R1.fastq.gz 2>/dev/null | wc -l) / 18"
echo "   MG  read pairs: $(ls "$IN"/*_MG_R1.fastq.gz  2>/dev/null | wc -l) / 10"
echo "Done."
