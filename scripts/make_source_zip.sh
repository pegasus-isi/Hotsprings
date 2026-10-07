#!/usr/bin/env bash
# Create a clean source ZIP while preserving the outer project folder.
#
# Special rule:
#   wf-output/ is included and files inside it may exceed MAX_MIB.
#
# Note:
#   Extension exclusions still apply inside wf-output/.
#   For example, *.rds files are still excluded.
#
# Usage:
#   ./make_source_zip.sh /path/to/subductcr-final
#   ./make_source_zip.sh /path/to/subductcr-final /path/to/output.zip

set -Eeuo pipefail

PROJECT_INPUT="${1:-.}"

MAX_MIB=100
MAX_BYTES=$((MAX_MIB * 1024 * 1024))

# ---------------------------------------------------------------------------
# Basic checks
# ---------------------------------------------------------------------------

if [[ ! -d "$PROJECT_INPUT" ]]; then
    echo "ERROR: project directory does not exist: $PROJECT_INPUT" >&2
    exit 1
fi

command -v zip >/dev/null 2>&1 || {
    echo "ERROR: zip is not installed" >&2
    exit 1
}

PROJECT_DIR="$(cd "$PROJECT_INPUT" && pwd -P)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
PROJECT_PARENT="$(dirname "$PROJECT_DIR")"

ARCHIVE_INPUT="${2:-$PROJECT_PARENT/${PROJECT_NAME}-source.zip}"

ARCHIVE_DIR="$(dirname "$ARCHIVE_INPUT")"
ARCHIVE_NAME="$(basename "$ARCHIVE_INPUT")"

mkdir -p "$ARCHIVE_DIR"

ARCHIVE_DIR="$(cd "$ARCHIVE_DIR" && pwd -P)"
ARCHIVE="$ARCHIVE_DIR/$ARCHIVE_NAME"

REPORT="$PROJECT_DIR/EXCLUDED_FILES.md"

MANIFEST="$(mktemp /tmp/${PROJECT_NAME}.zip-manifest.XXXXXX)"
LARGE_LIST="$(mktemp /tmp/${PROJECT_NAME}.large-files.XXXXXX)"

trap 'rm -f "$MANIFEST" "$LARGE_LIST"' EXIT

cd "$PROJECT_PARENT"

# ---------------------------------------------------------------------------
# Find files > MAX_MIB outside wf-output/
#
# Large files inside wf-output/ are intentionally allowed.
# ---------------------------------------------------------------------------

find "$PROJECT_NAME" \
    \( -type d \( \
       -name data \
       -o -name input \
       -o -name runs \
       -o -name wf-scratch \
       -o -name logs \
       -o -name condologs \
       -o -name 'Untitled Folder' \
       -o -name 16S_rRNA_data \
       -o -name mi-faser_metagenomes \
       -o -name .git \
       -o -name __pycache__ \
       -o -name .pytest_cache \
       -o -name .ipynb_checkpoints \
    \) \) -prune \
    -o \( \
       -type f \
       ! -path "$PROJECT_NAME/wf-output/*" \
       -size +"${MAX_BYTES}"c \
       -printf '%s\t%p\n' \
    \) \
    | sort -nr > "$LARGE_LIST"

# ---------------------------------------------------------------------------
# Generate exclusion report
# ---------------------------------------------------------------------------

{
    printf '# Excluded data and large files\n\n'

    printf 'This source archive preserves the `%s/` project directory structure.\n\n' \
        "$PROJECT_NAME"

    printf 'The `wf-output/` directory is included, and files inside it are allowed to exceed %s MiB.\n\n' \
        "$MAX_MIB"

    printf 'Elsewhere, datasets, raw sequencing files, generated workflow state, logs, archives, backups, and files larger than %s MiB are excluded.\n\n' \
        "$MAX_MIB"

    # -----------------------------------------------------------------------
    # Excluded directories
    # -----------------------------------------------------------------------

    printf '## Excluded directories\n\n'

    find "$PROJECT_NAME" \
        \( -type d \( \
           -name data \
           -o -name input \
           -o -name runs \
           -o -name wf-scratch \
           -o -name logs \
           -o -name condologs \
           -o -name 'Untitled Folder' \
           -o -name 16S_rRNA_data \
           -o -name mi-faser_metagenomes \
           -o -name .git \
           -o -name __pycache__ \
           -o -name .pytest_cache \
           -o -name .ipynb_checkpoints \
        \) \) \
        -prune \
        -printf '%p/\n' \
        | sort \
        | sed 's|^|- `|; s|$|`|'

    # -----------------------------------------------------------------------
    # Excluded file types
    # -----------------------------------------------------------------------

    printf '\n## Excluded archives, raw data, logs, and backup files\n\n'

    find "$PROJECT_NAME" \
        \( -type d \( \
           -name data \
           -o -name input \
           -o -name runs \
           -o -name wf-scratch \
           -o -name logs \
           -o -name condologs \
           -o -name 'Untitled Folder' \
           -o -name 16S_rRNA_data \
           -o -name mi-faser_metagenomes \
           -o -name .git \
           -o -name __pycache__ \
           -o -name .pytest_cache \
           -o -name .ipynb_checkpoints \
        \) \) -prune \
        -o \( \
           -type f \( \
              -name '*.zip' \
              -o -name '*.tar' \
              -o -name '*.tar.gz' \
              -o -name '*.tgz' \
              -o -name '*.fastq' \
              -o -name '*.fastq.gz' \
              -o -name '*.fq' \
              -o -name '*.fq.gz' \
              -o -name '*.sra' \
              -o -name '*.bam' \
              -o -name '*.sam' \
              -o -name '*.fasta' \
              -o -name '*.fa' \
              -o -name '*.fna' \
              -o -name '*.align' \
              -o -name '*.rds' \
              -o -name '*.RData' \
              -o -name '*.rda' \
              -o -name '*.log' \
              -o -name '*.out' \
              -o -name '*.err' \
              -o -name '*.lof' \
              -o -name '*.bkp' \
              -o -name '*-Copy*' \
              -o -name '*~' \
              -o -name tree \
              -o -name 'tree (*)' \
           \) \
           -printf '%p\n' \
        \) \
        | sort \
        | sed 's|^|- `|; s|$|`|'

    # -----------------------------------------------------------------------
    # Large files
    # -----------------------------------------------------------------------

    printf '\n## Large files excluded outside wf-output\n\n'

    if [[ -s "$LARGE_LIST" ]]; then

        printf '| File | Size |\n'
        printf '|---|---:|\n'

        while IFS=$'\t' read -r bytes path; do

            size_mib="$(
                awk -v bytes="$bytes" \
                    'BEGIN { printf "%.1f", bytes / 1048576 }'
            )"

            printf '| `%s` | %s MiB |\n' \
                "$path" "$size_mib"

        done < "$LARGE_LIST"

    else

        printf 'No additional files larger than %s MiB were found outside `wf-output/`.\n' \
            "$MAX_MIB"

    fi

    # -----------------------------------------------------------------------
    # Instructions
    # -----------------------------------------------------------------------

    printf '\n## Obtaining excluded data\n\n'

    printf 'Use `prepare_data.sh`, the data-preparation scripts under `bin/`, and the project `README.md` files to obtain or regenerate excluded data.\n'

} > "$REPORT"

# ---------------------------------------------------------------------------
# Build ZIP manifest
#
# Rules:
#
#   wf-output/
#       Included
#       Files may exceed 100 MiB
#       Extension exclusions still apply
#
#   Everywhere else
#       Maximum size = 100 MiB
#       Extension exclusions apply
#
# ---------------------------------------------------------------------------

find "$PROJECT_NAME" \
    \( -type d \( \
       -name data \
       -o -name input \
       -o -name runs \
       -o -name wf-scratch \
       -o -name logs \
       -o -name condologs \
       -o -name 'Untitled Folder' \
       -o -name 16S_rRNA_data \
       -o -name mi-faser_metagenomes \
       -o -name .git \
       -o -name __pycache__ \
       -o -name .pytest_cache \
       -o -name .ipynb_checkpoints \
    \) \) -prune \
    -o \( \
       -type d \
       -o -type l \
       -o \( \
          -type f \
          ! -name '*.zip' \
          ! -name '*.tar' \
          ! -name '*.tar.gz' \
          ! -name '*.tgz' \
          ! -name '*.fastq' \
          ! -name '*.fastq.gz' \
          ! -name '*.fq' \
          ! -name '*.fq.gz' \
          ! -name '*.sra' \
          ! -name '*.bam' \
          ! -name '*.sam' \
          ! -name '*.fasta' \
          ! -name '*.fa' \
          ! -name '*.fna' \
          ! -name '*.align' \
          ! -name '*.rds' \
          ! -name '*.RData' \
          ! -name '*.rda' \
          ! -name '*.log' \
          ! -name '*.out' \
          ! -name '*.err' \
          ! -name '*.lof' \
          ! -name '*.bkp' \
          ! -name '*-Copy*' \
          ! -name '*~' \
          ! -name tree \
          ! -name 'tree (*)' \
          \( \
             -path "$PROJECT_NAME/wf-output/*" \
             -o ! -size +"${MAX_BYTES}"c \
          \) \
       \) \
    \) \
    -print > "$MANIFEST"

# ---------------------------------------------------------------------------
# Create archive
# ---------------------------------------------------------------------------

rm -f "$ARCHIVE"

zip -q -y "$ARCHIVE" -@ < "$MANIFEST"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
echo "Created: $ARCHIVE"
echo "Included report: $PROJECT_NAME/EXCLUDED_FILES.md"
echo
echo "wf-output:"
echo "  Included"
echo "  Files larger than $MAX_MIB MiB are allowed"
echo
echo "Other project files:"
echo "  Maximum included size: $MAX_MIB MiB"
echo
echo "Excluded:"
echo "  data/"
echo "  input/"
echo "  runs/"
echo "  wf-scratch/"
echo "  logs/"
echo "  condologs/"
echo "  raw sequencing files"
echo "  archives/backups"
echo "  *.rds / *.RData / *.rda"
