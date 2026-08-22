#!/usr/bin/env bash
# rename_reads.sh -- rename downloaded metagenome reads to the library IDs the
# generator expects, and report which libraries are still missing.
#
# Run from the project root:  ./rename_reads.sh
# Safe: only renames when a file maps to exactly ONE target library.
set -euo pipefail
IN="input"

# The 37 metagenome libraries the generator expects (LIBS_MG).
TARGETS=(ARS BQF BQS BQS1 BR1F BRF1 BRF2 BRS1 BRS2 CYF CYS EPF EPS ESF9 ETS \
         FAS MTF PBS PFF PFS PGF PGS PLS QH2F QHS1 QHS2 QNF QNS RSF RSS RVF \
         SIF SIS SLF SLS TCF TCS)

# normalize a filename token to a candidate library: strip _MG_R.., trailing
# 6+ digit date, and separators.  e.g. BQF170218 -> BQF, AR170220 -> AR, BR -> BR
norm(){ echo "$1" | sed -E 's/_MG_R[12]\.fastq\.gz$//; s/[0-9]{6,}.*$//; s/[._-]+$//'; }

declare -A HAVE      # target -> source basename that satisfies it
echo "== renaming (unambiguous only) =="
for r1 in "$IN"/*_MG_R1.fastq.gz; do
  [ -e "$r1" ] || continue
  base="$(basename "$r1")"; token="$(norm "$base")"
  # find target libraries this token could be: exact, or unique prefix match
  matches=()
  for t in "${TARGETS[@]}"; do [ "$t" = "$token" ] && matches=("$t"); done
  if [ ${#matches[@]} -eq 0 ]; then
    for t in "${TARGETS[@]}"; do [[ "$t" == "$token"* ]] && matches+=("$t"); done
  fi
  if [ ${#matches[@]} -eq 1 ]; then
    tgt="${matches[0]}"
    for R in R1 R2; do
      src="$IN/${base/_MG_R1.fastq.gz/_MG_${R}.fastq.gz}"
      dst="$IN/${tgt}_MG_${R}.fastq.gz"
      if [ -e "$src" ] && [ "$src" != "$dst" ]; then mv -n "$src" "$dst" && echo "  $src -> $dst"; fi
    done
    HAVE[$tgt]="$base"
  elif [ ${#matches[@]} -gt 1 ]; then
    echo "  ? $base -> token '$token' is AMBIGUOUS (${matches[*]}); one file cannot cover multiple libraries -- leave for re-fetch"
  else
    echo "  ? $base -> token '$token' matches no target library -- check input/ena_MG.tsv"
  fi
done

echo; echo "== coverage: which of the 37 metagenome libraries are present =="
present=0; missing=()
for t in "${TARGETS[@]}"; do
  if [ -e "$IN/${t}_MG_R1.fastq.gz" ]; then echo "  OK   $t"; present=$((present+1));
  else echo "  MISS $t"; missing+=("$t"); fi
done
echo; echo "present: $present / ${#TARGETS[@]}   missing: ${#missing[@]}"
[ ${#missing[@]} -gt 0 ] && echo "missing libraries: ${missing[*]}"

echo; echo "NOTE: ambiguous/missing libraries were collapsed by the fetch (one file"
echo "      per site instead of per fluid/sediment/replicate library). To get them,"
echo "      re-fetch naming by library_name from input/ena_MG.tsv."