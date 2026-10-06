# Data sources — exact provenance

Every input, and exactly where it comes from.

## Fetched automatically (by bin/get_data.sh)

| File | Source | URL / accession |
|---|---|---|
| data/16s/kebj01_16s.fasta | NCBI KEBJ01 | https://www.ncbi.nlm.nih.gov/Traces/wgs/KEBJ01 |
| data/reference/silva_v132.db/.tax | mothur SILVA v132 | https://mothur.org/wiki/silva_reference_files/ |
| data/metagenome/*.fastq.gz | ENA PRJNA627197 | https://www.ebi.ac.uk/ena/browser/view/PRJNA627197 |
| data/reference/bac_*.csv, bac_tree.tre | GitHub dgiovannelli/SubductCR_16S-diversity | authors' repo |

## Bundled source tables

| File | Source |
|---|---|
| reference_data/ec_carbon.csv | Supplementary Table S14 (carbon-metabolism clique EC numbers) |
| reference_data/geochem.csv | Supplementary Tables S1–S4 (sample metadata, geochemistry, and flow-cytometry cell counts) |
| config/flux_params.yml | paper Methods (fixation rate, depth, porosity) |

## Built by get_data.sh from the above

| File | How |
|---|---|
| data/reference/ec_carbon.csv | staged from reference_data/ec_carbon.csv |
| data/reference/geochem.csv | staged from reference_data/geochem.csv |
| data/reference/cell_counts.csv | cell-count column extracted from reference_data/geochem.csv |
| data/reference/ena_map.tsv | sample<->run map, sample code parsed from each ENA library Name |

## Naming

Each metagenome library's Name (e.g. `TCF170221`) encodes the station code
(`TC`) + sample type (`F`=fluid, `S`=sediment) + a 6-digit date. The sample
code (`TCF`) is parsed automatically and matches the paper's station codes.

## Known gaps

- Raw 16S reads: never deposited (processed sequences in KEBJ01 are used instead; not required).
- Metagenome env data: 35/37 samples. `ARS` and `PBS` (stations AR, PB) are
  absent from all Supplementary Tables — a genuine gap in the published record.
