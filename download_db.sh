#!/usr/bin/env bash
# download_db.sh — download KOfam + UniRef50 databases to USC storage.
# Run on a USC login node (needs internet).
#   bash download_db.sh
set -euo pipefail

DB=/project/vahi_1862/hotspring/db
module load apptainer/1.5.4

mkdir -p "$DB/kofam_db" "$DB/mmseqs"

# ---- KOfam (~5 GB) ----
echo ">> KOfam"
cd "$DB/kofam_db"
[ -s ko_list ] || { wget -q --show-progress https://www.genome.jp/ftp/db/kofam/ko_list.gz && gunzip -f ko_list.gz; }
[ -d profiles ] || { wget -q --show-progress https://www.genome.jp/ftp/db/kofam/profiles.tar.gz && tar -xzf profiles.tar.gz; }

# ---- UniRef50 (~15 GB) ----
echo ">> UniRef50 (MMseqs2)"
cd "$DB/mmseqs"
[ -f mmseqs.sif ] || apptainer pull mmseqs.sif docker://swarmourr/mag-mmseqs:latest
[ -s uniref50.dbtype ] || apptainer exec mmseqs.sif mmseqs databases UniRef50 uniref50 tmp --threads 8

echo ""
echo "DONE."
echo "  KOfam:    $DB/kofam_db"
echo "  UniRef50: $DB/mmseqs/uniref50"
