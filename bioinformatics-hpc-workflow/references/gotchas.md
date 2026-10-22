# Operational Gotchas — the failures that cost days

Consult this before guessing when a run stalls. Each entry: the symptom, the
cause, the fix. These are learned by hitting them; knowing them up front saves
days.

## Queue / scheduler

**Symptom:** "More resources requested than allowed for logical queue
shared_... (1.125 > 0.5)"
**Cause:** the shared/small queue caps at a fraction of a node; a multi-core
job exceeds it.
**Fix:** put multi-core jobs on the full/regular queue (NERSC: regular; USC:
main). Keep only tiny (1-2 core) jobs on shared.

**Symptom:** jobs sit Idle for hours.
**Cause:** normal queue wait on a shared HPC, OR a scarce resource (GPU nodes
are scarcer than CPU), OR a job/association limit.
**Fix:** `squeue -u <user> -t PENDING --format="%.25j %.20R"` — the reason
column tells you (Priority/Resources = just wait; GPU-related = consider CPU).
Queue wait is normal HPC; not a failure.

**Symptom:** held job, "Error parsing classad or job not found".
**Cause:** usually a container not available, OR a lapsed credential, OR a
transient scheduler glitch.
**Fix:** check the container is pulled; refresh credentials; `condor_release`.

## Containers

**Symptom:** GPU container build fails on a laptop: "pytorch-gpu requires
__cuda which is missing on the system", or I/O errors / disk corruption.
**Cause:** building CUDA containers on a non-GPU host (a Mac). conda can't
resolve GPU PyTorch without a CUDA host; large CUDA images also corrupt
laptop Docker's virtual disk.
**Fix:** build GPU containers ON THE CLUSTER with podman-hpc (native x86,
real CUDA), or build CPU-only versions. Split the build: small CPU containers
on the laptop, big GPU ones on the cluster.

**Symptom:** "Unable to find curl/wget ... Unable to download the default
worker package" (PegasusLite fails inside the container).
**Cause:** the container lacks curl/wget, so the workflow worker package
can't be fetched inside it.
**Fix:** add curl+wget to every Dockerfile; also set the workflow to not
re-download the worker package (use the staged one).

**Symptom:** on a non-GPU build host, "GPU" PyTorch resolves to the CPU build.
**Cause:** no CUDA on the build host -> conda picks cpuonly PyTorch.
**Fix:** build on the cluster (real CUDA) for true GPU, or accept CPU.

## Databases / filesystems

**Symptom:** "KO list not exist: /global/homes/<user>/kofam_db/ko_list" (file
is there, job can't see it).
**Cause:** the container runtime (Shifter/Apptainer) does NOT mount the home
directory; the job can't read a DB in home.
**Fix:** put reference databases on a mounted filesystem (CFS or scratch),
never home. Point the path there.

**Principle:** big reference DBs (KOfam ~5 GB, UniRef50 ~15 GB, DRAM ~500 GB)
are READ IN PLACE by path, never staged per job. Keep them on shared storage
the runtime mounts; reference by absolute path.

**Principle:** download large DBs on a LOGIN node (has internet); compute
nodes have none. Use the tool's own downloader (e.g. `mmseqs databases
UniRef50 ...`) or wget, on the login node.

## Scripts

**Symptom:** a step exits 141.
**Cause:** SIGPIPE (128+13). With `set -e` + `pipefail`, a pipe whose reader
closes early (`zcat | head`) kills the script.
**Fix:** drop `-e` for that step, or wrap the pipe: `{ zcat f | head -n N ||
true; } | ...`. Or use a tool that doesn't pipe (seqtk sample).

**Symptom:** `python3: command not found` inside a container.
**Cause:** the container lacks python.
**Fix:** add python to that Dockerfile, OR rewrite the wrapper to use awk/perl
instead of python.

## Data-shape / biology

**Symptom:** downstream tool errors "No sequences found in the reference
FASTA" (e.g. CoverM on an empty MAGs file).
**Cause:** an upstream step legitimately produced nothing — e.g. binning on
sparse/subsampled data yields no MAGs, so the MAGs file is empty.
**Fix:** this is a VALID outcome, not a crash condition. Guard every step that
can receive empty input: if the input fasta has no `>` records, write an empty
output and exit 0 so the DAG continues.

**Symptom:** binning produces no bins even on real data.
**Cause:** too few contigs — usually because reads were subsampled too
aggressively (e.g. 500k pairs). Binning needs enough coverage/contigs.
**Fix:** use full reads for real binning. Subsample only to smoke-test the
pipeline mechanics, not to produce real MAGs. 5M+ pairs minimum if you must
subsample.

**Symptom:** metal/functional gene search returns zero hits despite genes
being present.
**Cause:** ID-type mismatch — the annotation produced one ID type (e.g.
UniRef accessions) but the reference gene list uses another (e.g. KO numbers).
**Fix:** make the annotation output the same ID type as the reference list.
For KO-based lists, annotate with KOfam/DRAM (gives KOs); match KO vs KO.

## Data location / staging

**Principle:** data on the SUBMIT host (e.g. ACCESS) is staged to the compute
HPC by the workflow manager (declare it as a replica on the submit site). Data
already on the compute HPC is referenced by path (declare it on the compute
site), not staged. Know which — staging a 15 GB DB every job is wasteful;
failing to stage submit-host reads breaks the run.

## Credentials

**Principle:** keep job-submission creds (e.g. NERSC SFAPI in
~/.superfacility, or plain Slurm on other systems) separate from
data-transfer creds (e.g. an sshproxy cert). Refresh short-lived certs
(sshproxy ~24 h) before a run. If a working workflow suddenly can't submit,
suspect an expired credential first.

## The meta-gotcha: test first

The most expensive mistake is scaling to the full dataset before proving the
pipeline on 1-2 samples. Every gotcha above is cheaper to hit on a 2-sample
test than on a 35-sample multi-day run. Always smoke-test first.
