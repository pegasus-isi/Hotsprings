#!/usr/bin/env bash
# Generate the DAG, then plan + submit it. Requires Pegasus 5.x + HTCondor.
set -euo pipefail
cd "$(dirname "$0")"

python3 noble_gas_workflow.py                 # -> noble-gas-reduction.yml + pegasus.properties

pegasus-plan \
    --conf pegasus.properties \
    --sites local \
    --sites-catalog sites.yml \
    --output-sites local \
    --dir work \
    --submit \
    noble-gas-reduction.yml

echo
echo "Monitor with:  pegasus-status -w work/*/*"
echo "Final file lands in:  output/GAS_PROCESS_reproduced.xlsx"
