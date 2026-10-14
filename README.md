# SubductCR Metagenome-to-Model Workflow

End-to-end Pegasus workflow: raw metagenomes (or existing MAGs) → MAGs →
annotation → metal-gene search → abundance → integrate with geochemistry →
predict metal potential.

## Contents
```
workflow/metagenome_to_model.py   the Pegasus generator (13 jobs)
bin/                              13 wrapper scripts (one per step)
containers/                       11 Dockerfiles + build.sh
data/reference/                   metal_genes.ref, geochemistry.csv (placeholders)
data/metagenome/                  <- put your 34 read-pairs here
data/mags/                        <- existing MAGs (optional, Path B)
docs/workflow_dag.png/pdf         the workflow diagram
run.sh                            convenience launcher (sets env + samples)
README.md
```

## Pipeline (matches the DAG in docs/)
Path A (raw reads):
  qc_trim(fastp) → assembly(MEGAHIT) → read_map(Bowtie2)
  → SemiBin2 + COMEBin + VAMB [GPU] → refine(DAS Tool) → MAGs
Path B: existing MAGs → annotation
Annotation: DRAM → MMseqs2 functional[GPU] → MMseqs2 metal search[GPU]
Abundance: CoverM → coverage
Integrate: merge (coverage + metal hits + geochemistry)
Predict:   metal potential (GPU if deep-learning)

## GPU vs CPU (Perlmutter)
GPU (-C gpu): SemiBin2, COMEBin, VAMB, MMseqs2 (func + metal), predict
CPU (-C cpu): fastp, MEGAHIT, Bowtie2, DAS Tool, DRAM, CoverM, merge

## Your data
Reads live in data/metagenome/<sample>_R1/R2.fastq.gz. run.sh auto-detects the
sample names from that folder. The 34 SubductCR samples are also baked in as a
default (ARS ... TCS; QHS1 excluded).

## Run
```bash
# 1. build + push containers (on a Docker machine):
./containers/build.sh swarmourr latest
# 2. pull into Shifter (Perlmutter):
for t in qc assembly map semibin comebin vamb refine dram mmseqs coverm r; do
  shifterimg pull docker:swarmourr/mag-$t:latest; done
# 3. put reads in data/metagenome/ ; set databases ; then:
./run.sh                 # plan + submit
./run.sh --plan-only     # build the DAG only
```

## Databases to provide on the cluster
- MMseqs2 functional DB   (export MAG_FUNC_DB=...)
- DRAM databases          (DRAM setup)
- your curated metal-gene list → replace data/reference/metal_genes.ref

## Notes
- GPU: set MAG_GPU=1 (run.sh does this) so SemiBin2/VAMB/MMseqs2 use the GPU.
- Containers are NOT pre-built — build them with containers/build.sh.
- integrity.checking = none, so wrapper edits don't need checksum updates.
