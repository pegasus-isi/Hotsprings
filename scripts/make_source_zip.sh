#!/usr/bin/env bash
# Create a clean source-only ZIP while preserving the complete outer project
# folder structure.
#
# Usage:
#   ./make_source_zip.sh /path/to/subductcr-final
#   ./make_source_zip.sh /path/to/subductcr-final /path/to/output.zip

set -Eeuo pipefail

PROJECT_INPUT="${1:-.}"
MAX_MIB=100
MAX_BYTES=$((MAX_MIB * 1024 * 1024))

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

# Find large files outside the directories already excluded above.
find "$PROJECT_NAME" \
    \( -type d \( -name data \
       -o -name input \
       -o -name runs \
       -o -name wf-output \
       -o -name wf-scratch \
       -o -name logs \
       -o -name condologs \
       -o -name 'Untitled Folder' \
       -o -name 16S_rRNA_data \
       -o -name mi-faser_metagenomes \
       -o -name .git \
       -o -name __pycache__ \
       -o -name .pytest_cache \
       -o -name .ipynb_checkpoints \) \) -prune \
    -o -type f -size +"${MAX_BYTES}"c -printf '%s\t%p\n' \
    | sort -nr > "$LARGE_LIST"

# This report is deliberately included in the archive.
{
    printf '# Excluded data and large files\n\n'
    printf 'This source archive preserves the `%s/` project directory structure but excludes datasets, raw sequencing files, generated workflow state, old archives/backups, logs, and files larger than %s MiB.\n\n' \
        "$PROJECT_NAME" "$MAX_MIB"
    printf '## Excluded directories\n\n'
    find "$PROJECT_NAME" \
        \( -type d \( -name data \
           -o -name input \
           -o -name runs \
           -o -name wf-output \
           -o -name wf-scratch \
           -o -name logs \
           -o -name condologs \
           -o -name 'Untitled Folder' \
           -o -name 16S_rRNA_data \
           -o -name mi-faser_metagenomes \
           -o -name .git \
           -o -name __pycache__ \
           -o -name .pytest_cache \
           -o -name .ipynb_checkpoints \) \) \
        -prune -printf '- `%p/`\n' | sort

    printf '\n## Excluded archives, raw data, logs, and backup files\n\n'
    find "$PROJECT_NAME" \
        \( -type d \( -name data \
           -o -name input \
           -o -name runs \
           -o -name wf-output \
           -o -name wf-scratch \
           -o -name logs \
           -o -name condologs \
           -o -name 'Untitled Folder' \
           -o -name 16S_rRNA_data \
           -o -name mi-faser_metagenomes \
           -o -name .git \
           -o -name __pycache__ \
           -o -name .pytest_cache \
           -o -name .ipynb_checkpoints \) \) -prune \
        -o -type f \( -name '*.zip' \
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
           -o -name 'tree (*)' \) \
        -printf '- `%p`\n' | sort

    printf '\n## Large files excluded outside those directories\n\n'
    if [[ -s "$LARGE_LIST" ]]; then
        printf '| File | Size |\n|---|---:|\n'
        while IFS=$'\t' read -r bytes path; do
            size_mib="$(awk -v bytes="$bytes" 'BEGIN { printf "%.1f", bytes / 1048576 }')"
            printf '| `%s` | %s MiB |\n' "$path" "$size_mib"
        done < "$LARGE_LIST"
    else
        printf 'No additional files larger than %s MiB were found.\n' "$MAX_MIB"
    fi
    printf '\n## Obtaining excluded data\n\n'
    printf 'Use `prepare_data.sh`, the data-preparation scripts under `bin/`, and the project `README.md` files to obtain or regenerate excluded data.\n'
} > "$REPORT"

# Include directories explicitly so empty source directories and all folder
# names are retained. Store symlinks as symlinks instead of following them.
find "$PROJECT_NAME" \
    \( -type d \( -name data \
       -o -name input \
       -o -name runs \
       -o -name wf-output \
       -o -name wf-scratch \
       -o -name logs \
       -o -name condologs \
       -o -name 'Untitled Folder' \
       -o -name 16S_rRNA_data \
       -o -name mi-faser_metagenomes \
       -o -name .git \
       -o -name __pycache__ \
       -o -name .pytest_cache \
       -o -name .ipynb_checkpoints \) \) -prune \
    -o \( -type d -o -type l \
       -o \( -type f \
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
          ! -size +"${MAX_BYTES}"c \) \) -print \
    > "$MANIFEST"

rm -f "$ARCHIVE"
zip -q -y "$ARCHIVE" -@ < "$MANIFEST"

echo "Created: $ARCHIVE"
echo "Included report: $PROJECT_NAME/EXCLUDED_FILES.md"
echo "Excluded: data, generated workflow state, logs, archives, and backups"
echo "Maximum included file size: $MAX_MIB MiB"
