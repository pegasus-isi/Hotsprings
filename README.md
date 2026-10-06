# SubductCR — End-to-End Reproducible Workflow

A complete, ready-to-run [Pegasus WMS](https://pegasus.isi.edu) workflow that
reproduces the analysis of **Fullerton et al. 2021**
([Nature Geoscience](https://doi.org/10.1038/s41561-021-00725-0)) — the 16S and
metagenomic study of Costa Rican convergent-margin hot springs — from public
data. Developed in collaboration with the original authors.

---

## The workflow

```
16S track :  KEBJ01 processed sequences  ─┐
                                          ├─►  integrate with geochemistry  ─►  figures + report
MG  track :  ENA metagenome reads         ─┘
```

![SubductCR Pegasus workflow DAG](docs/workflow_dag.png)

The 16S branch starts from the processed 16S sequences at NCBI (KEBJ01) — no
raw reads needed. SILVA is used directly from mothur. The metagenome branch
processes the ENA reads through enzyme annotation.

---

## Run it in three commands

```bash
make containers    # 1. build the container images (once)
make data          # 2. download & organize every input
make run           # 3. plan + submit the workflow
```

## Already have the data?

If you already have the reads / SILVA / tables (under any naming), point the
project at them — it checks what exists, normalizes the names, and downloads
only what's missing:

```bash
make check   INPUT=/path/to/your/input    # report what's found / missing
make prepare INPUT=/path/to/your/input    # normalize names + fetch only gaps
make plan                                 # verify the DAG
make run                                  # go
```

`prepare` understands common naming variants automatically, e.g.
`CYF_MG_R1.fastq.gz` → `CYF_R1.fastq.gz`, and `silva.nr_v132.align` →
`silva_v132.db`. It never re-downloads anything you already have.

---

Choose where it runs:

```bash
export SUBDUCTCR_USE_SIF=1       # ACCESS (Singularity)
export SUBDUCTCR_USE_SHIFTER=1   # NERSC Perlmutter (Shifter)
# default: Docker Hub images
```

---

## Where every input comes from

`make data` (i.e. `bin/get_data.sh`) fetches and organizes everything:

| Input | Source | Fetched by |
|---|---|---|
| 16S processed sequences | **NCBI** KEBJ01 | `get_data.sh 16s` |
| SILVA v132 reference | **mothur** | `get_data.sh silva` |
| Metagenome reads (35 libraries) | **ENA** PRJNA627197 | `get_data.sh reads` |
| Authors' deposited 16S tables | **GitHub** dgiovannelli | `get_data.sh github` |
| Site geochemistry | **Suppl. Tables S1–S3** via `reference_data/geochem.csv` | `get_data.sh geochem` |
| Cell counts | **Suppl. Table S4** via `reference_data/geochem.csv` | `get_data.sh geochem` |
| Carbon-fixation EC list | **Suppl. Table S14** via `reference_data/ec_carbon.csv` | `get_data.sh geochem` |

Sample codes are read from each ENA library Name (e.g. `TCF170221` → `TCF`),
matching the paper's station codes automatically.

---

## Project layout

```
subductcr/
├── Makefile                   # one-command operations
├── workflow/end_to_end.py     # the Pegasus generator (one readable file)
├── bin/
│   ├── get_data.sh            # fetch + organize ALL inputs
│   ├── mothur_asv             # 16S: sequences -> ASV table
│   ├── filter_normalize       # 16S: clean + normalize
│   ├── asv_network            # 16S: co-occurrence cliques
│   ├── nmds_adonis            # 16S: ordination + PERMANOVA
│   ├── clique_geochem         # 16S: cliques vs environment
│   ├── trim_reads             # MG: quality-trim reads
│   ├── mifaser                # MG: enzyme annotation
│   ├── gene_merge             # MG: merge carbon-fixation ECs
│   ├── gene_network           # MG: gene cliques
│   ├── gene_geochem           # MG: gene cliques vs environment
│   ├── carbon_flux            # carbon-flux estimate
│   └── make_report            # assemble HTML report
├── containers/
│   ├── Dockerfile.r           # R 4.3.3 + pinned libraries
│   ├── Dockerfile.mothur
│   ├── Dockerfile.mifaser
│   └── build.sh
├── config/
│   ├── flux_params.yml        # carbon-flux parameters (paper Methods)
│   └── sample_station_map.tsv # sample -> station -> type
├── reference_data/            # bundled source tables + original analysis code
│   ├── ec_carbon.csv          # carbon-fixation EC list from Suppl. Table S14
│   └── geochem.csv            # sample geochemistry + cell counts
├── data/
│   ├── 16s/                   # KEBJ01 sequences (fetched)
│   ├── metagenome/            # ENA reads (fetched)
│   └── reference/
│       ├── ec_carbon.csv           # staged from reference_data/
│       ├── geochem.csv             # staged from reference_data/
│       ├── cell_counts.csv         # derived from reference_data/geochem.csv
│       ├── silva_v132.db|.tax      # fetched from mothur
│       └── ena_map.tsv             # sample<->run map (built from ENA)
└── docs/data_sources.md       # exact provenance of every input
```

---

## Software versions (verified)

| Component | Version |
|---|---|
| R | 4.3.3 (Bioconductor 3.18 base) |
| phyloseq, microbiome | Bioconductor 3.18 |
| Deriv | 4.1.3 (pinned; later needs R ≥ 4.4) |
| vegan, igraph, ggplot2, yaml | current CRAN, R 4.3.3-compatible |
| mothur, trimmomatic | Ubuntu 22.04 |
| mi-faser | GS+ database |

---

## Data completeness

- **16S:** fully reproducible (processed sequences + deposited tables).
- **Metagenome environmental data:** **35 of 37** samples. Two samples (`ARS`,
  `PBS` — stations AR, PB) have no geochemistry in the published Supplementary
  Tables; this is a genuine gap in the public record, not a naming issue.
- **Validation:** the Supplementary Tables also contain the expected results
  (clique compositions S14, correlations S15–S17), so a reproduction can be
  checked against the paper directly.

The bundled source tables under `reference_data/` mean the workflow needs **no
manual data entry** — runtime copies under `data/reference/` are staged
automatically.
