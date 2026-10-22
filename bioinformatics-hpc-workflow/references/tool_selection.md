# Tool Selection — reason from data + resources + goal

Apply these to the user's actual situation. Always: pick -> state the tradeoff
-> give the fallback if the fit is wrong.

## Assembly (reads -> contigs)
| Tool | Choose when | Avoid when | Gotcha |
|------|-------------|------------|--------|
| MEGAHIT | memory-limited, fast, large/complex data | need max contiguity | safe default |
| metaSPAdes | quality matters, ample memory | very large samples | OOM on big samples (>5-6 GB reads) |
| MetaHipMer2 | HPC-scale, many nodes | small jobs, no HPC build | HPC-build only |

Decision: memory<64GB or reads>5GB -> MEGAHIT; quality+ample memory -> metaSPAdes;
huge data+real allocation -> MetaHipMer2; else MEGAHIT.

## Read mapping
Bowtie2 (standard), minimap2 (fast/long reads), strobealign (very fast).
Always index the BAM (.bai) and declare it as a workflow output — binners need it.

## Binning (contigs -> MAGs)
| Tool | Choose when | Avoid when | Gotcha |
|------|-------------|------------|--------|
| MetaBAT2 | CPU-only, fast, reliable | want max quality + have GPU | no GPU needed — safest |
| SemiBin2 | GPU + can build GPU containers | no GPU infra | deep-learning; CUDA PyTorch |
| VAMB | GPU, autoencoder | no GPU | needs --cuda |
| COMEBin | GPU, contrastive | no GPU | newest; heavy to build |

Decision: no GPU / can't build GPU containers -> MetaBAT2 (CPU);
GPU + buildable -> SemiBin2 (best); ensemble -> SemiBin2+MetaBAT2(+VAMB/COMEBin) -> DAS Tool;
budget-limited -> single binner.
GPU reality: DL binners need CUDA PyTorch; won't resolve on a non-GPU host — build on
the cluster (podman-hpc) or use MetaBAT2.

## Refinement / dereplication
DAS Tool / MAGScoT (consolidate multi-binner bins), CheckM2 (quality),
dRep (dereplicate MAGs ACROSS samples — only if you want a unified catalog).

## Taxonomy
GTDB-Tk (classification; DB ~100 GB — only if needed).

## Functional annotation (MAGs -> genes)
| Tool | Gives | DB size | GPU |
|------|-------|---------|-----|
| Prodigal | gene prediction | — | — |
| KOfam | KO numbers | ~5 GB | — |
| MMseqs2 | homology (UniRef/NR) | 15-200 GB | optional (~20x) |
| DRAM | metabolism | ~500 GB | — |
| eggNOG | broad function | ~50 GB | — |

If a curated gene list is KO-based -> KOfam (5 GB, gives KOs). Don't pull 500 GB DRAM
just for KOs. If UniRef-based -> MMseqs2 vs UniRef50.
CRITICAL: annotation ID type MUST match the reference list (KO vs UniRef) or all matches
are empty.

## Abundance
CoverM (maps reads to MAGs -> per-sample abundance).

## Prediction / modeling
The scientist's domain. The skill scaffolds the integrated table; the predictive model
(what to predict, validation) is a research decision — don't ship a placeholder as a model.

## GPU vs CPU
GPU genuinely helps only: DL binners + MMseqs2. Everything else is CPU. Don't request GPU
for jobs that don't use it (lengthens queue waits). A fully-CPU run (MetaBAT2 + CPU MMseqs)
is a legitimate, simpler choice if GPU container setup is a barrier.
