# Getting & Organizing the Data

Before a workflow runs, the inputs must be fetched from public archives and
laid out where the generator expects them. This is often half the battle.

## Where bioinformatics data lives (public archives)

| Data type | Archive | How to get it |
|-----------|---------|---------------|
| Raw reads (metagenome/genome) | ENA, NCBI SRA | accession -> fastq.gz |
| 16S / amplicon | NCBI, SILVA (ref) | accession / curated FASTA |
| Assembled genomes / MAGs | NCBI, JGI IMG | download FASTA |
| Reference DBs | per-tool (UniRef, KOfam, GTDB) | tool downloader / wget |
| Supplementary data (geochem, metadata) | the paper's supplement | CSV/XLSX from the journal |

## Resolving accessions to files

**ENA (fastest for reads):** the ENA API gives direct fastq FTP/HTTPS URLs for
a run/sample accession. Build a sample -> URL map, then download. ENA URLs are
stable and support parallel download.

**NCBI SRA:** use the SRA toolkit (`prefetch` + `fasterq-dump`) to pull runs by
accession, then gzip. Slower than ENA but comprehensive.

**Verify before you commit:** check every URL resolves (a quick HEAD request)
and that sample<->accession mapping is correct BEFORE downloading GBs. A
mismatched or swapped accession wastes hours. Watch for naming quirks (a
sample called BR2F in one table and BRF2 in another — build a canonical
matcher).

## Download on the right host

- Download on a LOGIN node (internet) or the submit host — compute nodes have
  no internet.
- Reads can be staged to the compute cluster by the workflow (if on the submit
  host) OR pre-placed on cluster storage (then referenced by path). See the
  gotchas on data location.
- Large downloads: parallelize, resume on failure, verify sizes/checksums.

## Organizing the layout

Keep a predictable structure the generator points at:
```
project/
├── data/
│   ├── reads/            <sample>_R1.fastq.gz, <sample>_R2.fastq.gz   (raw reads)
│   ├── mags/             <mag>.fasta                                   (existing MAGs)
│   └── reference/        metal_genes.ref, geochemistry.csv, small refs
├── workflow/             the generator
├── bin/                  wrapper scripts
└── containers/           Dockerfiles (+ sif/ for Apptainer)
```
Big reference DBs (UniRef, KOfam, GTDB) go on shared cluster storage
(CFS/scratch), NOT in the project — referenced by absolute path.

## Naming consistency (critical)

The generator matches samples by filename. Make the sample IDs in:
- the read filenames (`<sample>_R1.fastq.gz`),
- the metadata/geochemistry table (the `sample` column),
- the sample list in the generator
...all use the SAME IDs. Mismatches mean the merge/join silently drops samples
(NA for metadata). If the metadata uses long IDs (e.g. VAMPS-style
`DCO_LLO_Bv4v5..CYF_CY170214`), extract the short code (`CYF`) into a clean
`sample` column first.

## Subsampling (only for smoke tests)

To smoke-test the pipeline mechanics quickly, subsample reads (seqtk sample,
or a SIGPIPE-safe zcat|head). But: aggressive subsampling (e.g. 500k pairs)
STARVES assembly/binning and produces no MAGs. Use full reads for real runs;
subsample only to validate the DAG wiring, and even then keep it generous
(5M+ pairs) if you want binning to produce anything.

## Metadata / geochemistry for downstream joins

If the workflow joins results with sample metadata (environmental variables,
geochemistry), prepare that CSV with a clean `sample` key matching the reads,
numeric columns for the variables, and one row per sample. Samples without a
metadata row get NA on join — that's fine, but know which samples that affects.
