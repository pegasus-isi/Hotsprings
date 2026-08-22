# SubductCR &mdash; Pegasus workflow

A [Pegasus WMS](https://pegasus.isi.edu) rebuild of the computational pipeline
from **Fullerton et al. (2021)**, *"Effect of tectonic processes on
biosphere&ndash;geosphere feedbacks across a convergent margin"*
([Nat. Geosci.](https://doi.org/10.1038/s41561-021-00725-0)).

The wet-lab stages (sampling, DNA extraction, MiSeq/NextSeq sequencing) are **not**
in the workflow &mdash; they produce the raw reads declared as inputs. Everything
from the reads onward is expressed as a DAG of containerised jobs.

## The DAG

Two parallel tracks fan out per sequencing library and then merge:

```
 16S:  qc_16s[x32] -> mothur_asv -> filter_normalize -> asv_network -> clique_geochem
 MG:   trim_reads[x37] -> mifaser[x37] -> gene_merge -> gene_network -> gene_geochem
                                          \
 shared:  filter_normalize -> nmds_adonis  }-> make_report
          (cell_counts,geochem) -> carbon_flux
```

Render it: `make dag` (produces `subductcr_dag.pdf` / `.png`).

## Layout

```
subductcr_workflow.py   Pegasus generator: catalogs + DAG (edit SAMPLES here)
gen_dag.py              standalone Graphviz DAG renderer
bin/                    13 job wrappers (tool + R stages)
input/                  raw reads, reference DBs, flux_params.yml, samples.csv
reference_data/         authors' published tables + original code (CC-BY 4.0)
containers/             Dockerfile.r + image notes
conf/                   (reserved for site overrides)
Makefile                catalogs / plan / dag / test-analysis / clean
```

## Jobs

| Job | Tool / method | Fan-out | In &rarr; Out |
|-----|---------------|---------|---------------|
| `qc_16s` | vsearch merge + UCHIME | per lib | reads &rarr; clean.fasta |
| `mothur_asv` | mothur (SILVA v132) | merge | fastas+silva &rarr; ASV table, taxonomy |
| `filter_normalize` | phyloseq | &mdash; | ASV table &rarr; filtered.rds |
| `asv_network` | Spearman &rho;>0.7 + Louvain | &mdash; | filtered &rarr; ASV cliques |
| `clique_geochem` | VSURF + cor.test | &mdash; | cliques+geochem &rarr; clique&ndash;env |
| `trim_reads` | Trimmomatic | per lib | reads &rarr; trimmed |
| `mifaser` | mi-faser (GS+) | per lib | trimmed+db &rarr; EC counts |
| `gene_merge` | merge + normalise | merge | EC counts &rarr; gene table |
| `gene_network` | Spearman &rho;>0.5 + Louvain | &mdash; | gene table &rarr; gene-cliques |
| `gene_geochem` | cor.test | &mdash; | gene-cliques+geochem &rarr; env |
| `nmds_adonis` | vegan NMDS + adonis | &mdash; | filtered+geochem &rarr; Fig.2 |
| `carbon_flux` | Magnabosco integ. + Eqs 1-4 | &mdash; | cells+geochem+params &rarr; flux |
| `make_report` | HTML assembly | converge | all &rarr; report.html |

Pegasus infers every edge from the `add_inputs`/`add_outputs` files &mdash; you
never wire the arrows by hand. `mothur_asv` waits for all `qc_16s` jobs because it
lists their outputs as inputs; `make_report` is the terminal node.

## Run

```bash
pip install -r requirements.txt          # needs Pegasus 5.x + Graphviz
# 1. put reads + reference DBs in input/  (see input/README.md)
# 2. build + push the container images to Docker Hub:
make images                              # ./containers/build_and_push.sh swarmourr
# 3. generate catalogs + abstract workflow.yml:
make catalogs
# 4a. plan + submit using Docker images:
make plan
# --- OR, on an HPC cluster with Singularity/Apptainer (Route A): ---
# 2b. build .sif from the Hub images into containers/sif/:
make sif                                 # ./containers/build_sif.sh swarmourr
# 4b. plan + submit using the .sif files:
make plan-sif                            # sets SUBDUCTCR_USE_SIF=1
```

Container backend is chosen at plan time by the `SUBDUCTCR_USE_SIF` env var:
unset/`0` = Docker images from Docker Hub; `1` = local `.sif` files under
`containers/sif/`. See `containers/README.md`.

`subductcr_workflow.py` targets a `condorpool` execution site with results staged
back to `local`. Swap the Site definitions in `build_site_catalog()` for SLURM,
a cloud, or an OSG access point without touching the DAG.

## Notes

- The single "correlate geochemistry" idea from the paper is split into two real
  jobs (`clique_geochem`, `gene_geochem`) because ASV cliques and gene-cliques are
  tested against geochemistry separately.
- `nmds_adonis` branches off `filter_normalize` (it needs the community table, not
  the correlation output).
- Resource requests (cores, memory, walltime) are set per Transformation via
  Condor/Pegasus profiles &mdash; tune for your data volume.
- See `ATTRIBUTION.md`. Data/code from the authors' repo are CC-BY 4.0.
