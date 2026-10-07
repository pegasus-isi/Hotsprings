# Noble-Gas Reduction Workflow

Standalone Python workflow for reproducing the calculated noble-gas workbook
tabs from an Excel source workbook. The script copies the workbook through,
recomputes the calculated tabs in Python, and writes an output workbook for
comparison or review.

## Repository Layout

```text
.
├── data/
│   └── Oct2026_GAS_PROCESS_source.xlsx
├── docs/
│   └── Reproducing_the_Noble-Gas_Pipeline_in_Python.pdf
├── outputs/
│   └── oct_tabs_generated.xlsx
├── workflow/
│   ├── noble_gas_workflow.py
│   ├── noble-gas-reduction.yml
│   ├── input/GAS_PROCESS.xlsx
│   ├── bin/
│   └── README.md
├── src/
│   └── noble_gas_reducer.py
├── requirements.txt
└── README.md
```

## Files

| Path | Purpose |
|---|---|
| `src/noble_gas_reducer.py` | Python implementation of the tab-reproduction workflow |
| `data/Oct2026_GAS_PROCESS_source.xlsx` | Source workbook used as workflow input |
| `outputs/oct_tabs_generated.xlsx` | Generated workbook snapshot |
| `docs/Reproducing_the_Noble-Gas_Pipeline_in_Python.pdf` | Companion pipeline documentation |
| `workflow/` | Pegasus workflow package for the noble-gas reduction pipeline |

## Additional Pegasus Workflow

`workflow/` is included as a separate workflow package in this
branch. It contains a Pegasus 5.x abstract workflow, DAG images, a local site
catalog, stage scripts under `bin/`, and its own input workbook under
`workflow/input/GAS_PROCESS.xlsx`.

See `workflow/README.md` for the workflow DAG, Pegasus planning
steps, and standalone stage-by-stage run commands.

## Setup

Use Python 3.9 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Regenerate the default output workbook:

```bash
python src/noble_gas_reducer.py
```

Run with explicit input and output paths:

```bash
python src/noble_gas_reducer.py \
  data/Oct2026_GAS_PROCESS_source.xlsx \
  outputs/oct_tabs_generated.xlsx
```

Write one workbook per reproduced tab:

```bash
python src/noble_gas_reducer.py \
  data/Oct2026_GAS_PROCESS_source.xlsx \
  outputs/tabs \
  --separate
```

## What The Script Reproduces

- `Semi Raw`: validates paste-to-semi-raw joins while preserving manual
  overrides.
- `Blanks`: reproduces the selected blank average row.
- `Air STDs`: reproduces blank-corrected columns, ratio columns, and the
  average row.
- `Samples`: reproduces concentration columns and simple ratio columns.

All other workbook sheets and cells are copied through from the source workbook.
