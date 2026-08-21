# Input files

Place these before running the workflow. Logical names must match the
replica catalog built in `subductcr_workflow.py`.

## Per-sample raw reads (from SRA)
- `<SAMPLE>_16S_R1.fastq.gz`, `<SAMPLE>_16S_R2.fastq.gz`  (BioProject PRJNA579365)
- `<SAMPLE>_MG_R1.fastq.gz`,  `<SAMPLE>_MG_R2.fastq.gz`   (BioProject PRJNA627197)

## References
- `silva_v132.db` — SILVA v132 reference alignment + taxonomy (mothur format)
- `gsplus.db`     — mi-faser Gold-Standard-Plus database

## Tables (provided as test inputs under ../reference_data/)
- `geochem.csv`      — environmental + geochemistry table (SubductCR_bac_sample_table.csv)
- `cell_counts.csv`  — flow-cytometry cell densities
- `flux_params.yml`  — carbon-flux parameters (already here)

## Quick test without sequencing
The authors' published count tables let you exercise the analysis half of the
DAG without raw reads. See `../Makefile` target `test-analysis`.
