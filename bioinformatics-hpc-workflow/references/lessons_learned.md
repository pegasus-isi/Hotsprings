# Lessons Learned — the full operational playbook

Everything learned building and running real HPC bioinformatics workflows end
to end, organized by phase. This is the narrative companion to gotchas.md
(quick lookup) — read this to understand the WHY and the sequence.

## Phase 0 — before you build

- **A reproduction is not always a reproduction.** Re-deriving results from a
  paper may require the authors' exact method (e.g. per-sample grouping in
  amplicon dereplication). Matching the METHOD matters more than matching the
  tool invocation. But reach the method by the most reliable route — if a tool
  step is fragile, a small deterministic script that does the same thing is
  fine.
- **Know your data types.** 16S amplicons (a marker gene, FASTA, "who's
  there") and shotgun metagenomes (all DNA, FASTQ pairs, "what they can do")
  are different data with similar filenames. Don't conflate them.
- **Define the science goal before the pipeline.** "Predict metal cycling" is
  a research question, not a pipeline step. The pipeline can scaffold the
  inputs (an integrated table); the predictive model is the scientist's call.
  Don't ship a placeholder ranking as if it were a validated model.

## Phase 1 — getting the data

- Resolve accessions to files via ENA (fast, stable URLs) or SRA toolkit.
- VERIFY sample<->accession mapping before downloading GBs. Watch for naming
  swaps across tables (BR2F vs BRF2) — build a canonical matcher.
- Download on a login/submit node (internet); compute nodes have none.
- Keep sample IDs identical across read filenames, metadata table, and the
  generator's sample list — joins silently drop mismatches.

## Phase 2 — building the workflow

- One generator wires inputs -> jobs -> outputs. Keep it one readable file.
- Per-sample jobs fan out (assembly, binning, annotation per sample); only the
  final merge/predict combine across samples. Know which steps combine.
- Register containers in the transformation catalog or you get "non existent
  container".
- Resolve all paths to absolute in wrappers (tools cd internally).
- integrity.checking=none saves endless checksum edits when you tweak wrappers
  mid-run.

## Phase 3 — containers

- Split the build: small CPU containers on a laptop; big GPU containers on the
  cluster (podman-hpc). Building CUDA on a Mac fails (cpuonly resolution) and
  corrupts Docker's disk.
- Every container needs curl+wget (worker package download inside it).
- Shifter: shifter:/// (three slashes, empty host) keeps the full namespace.
- Apptainer: pull to .sif; GPU needs --nv.

## Phase 4 — databases

- Big DBs (KOfam 5 GB, UniRef50 15 GB, GTDB 100 GB, DRAM 500 GB) live on a
  runtime-mounted filesystem (CFS/scratch), NOT home (Shifter/Apptainer don't
  mount home). Reference by absolute path; read in place, never staged.
- Download on a login node. Use the tool's downloader (mmseqs databases ...).
- Pick the RIGHT db: for a KO-based gene list, KOfam (5 GB) beats DRAM (500 GB)
  — don't pull half a terabyte for KOs you can get in 5 GB.
- Match ID types: KO list needs KO annotation; UniRef hits won't match KOs.

## Phase 5 — scheduler / queues

- The shared/small queue caps at a fraction of a node; multi-core jobs must use
  the full/regular queue or you get "more resources than allowed".
- GPU is only worth requesting for the DL binners and MMseqs. Requesting GPU
  for CPU work just lengthens queue waits.
- Idle jobs for hours are usually normal queue wait on a shared HPC, not a
  failure. squeue -t PENDING shows the reason.
- Held "Error parsing classad" is usually a missing container or lapsed
  credential.

## Phase 6 — credentials & data movement

- Separate submission creds (SFAPI in ~/.superfacility, or plain Slurm) from
  data-transfer creds (sshproxy cert ~/.ssh/nersc, ~24 h — refresh before runs).
- Submit-host data is STAGED by the workflow; cluster-resident data is
  referenced by PATH. Know which for each input.
- A transfer PRE-check (sshproxy validity) can live in a transfer
  transformation to catch an expired cert before a run stalls.

## Phase 7 — testing & scaling

- TEST FIRST on 1-2 samples, end to end, before the full set. Every gotcha is
  cheaper on a 2-sample test than a 35-sample multi-day run.
- Use FULL reads for a meaningful test. Aggressive subsampling (500k pairs)
  starves assembly/binning -> no MAGs. Subsample only to validate DAG wiring.
- Expect a full metagenomic run to span 1-2 DAYS (queue waits + real compute),
  not hours. The compute is hours; the wall-clock is scheduling.
- Resumability is the payoff: fix one script, resume; only the changed step and
  its dependents re-run. The expensive upstream (assembly/binning) is kept.
  This is what makes multi-day, multi-step reproduction practical.

## Phase 8 — debugging discipline

- Read the actual error before changing anything. Exit codes are signals:
  137 = OOM (more memory), 141 = SIGPIPE (pipe/`set -e`), 1 = app error
  (read the stderr), held = scheduler/container/credential.
- When a step "produces nothing," ask whether that's a VALID outcome (empty
  MAGs from sparse data) and guard it, vs. a real bug.
- Fix at the right layer: a logic bug is in the wrapper; a resource issue is in
  the transformation; a system issue is in the site profile — not all in one.
- Don't fight a fragile tool step forever. If unique.seqs over-collapses, a
  deterministic dereplication script reaching the same scientific result is
  legitimate.

## The meta-lessons

- **AI + HPC is a loop:** plan -> run -> read logs -> diagnose -> adjust. Turn
  execution history into the next planning signal (an OOM once -> more memory
  next time).
- **The scientist stays in control.** The tooling accelerates the engineering
  (searching, writing, debugging); it does not replace scientific judgment
  (which method, what the results mean).
- **Portability is a profile, not a rewrite.** The same workflow runs on any
  HPC Pegasus supports; only the site profile (runtime, queues, gpu_arg, paths)
  changes.
