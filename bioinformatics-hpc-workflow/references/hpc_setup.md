# HPC Setup — containers, databases, credentials

## Containers
- Build SMALL CPU containers on a laptop (micromamba/conda base).
- Build BIG GPU containers ON THE CLUSTER with podman-hpc (native x86, real
  CUDA) — NOT on a laptop (CUDA won't resolve; big images corrupt Docker).
- Every container needs curl+wget (for the worker package).
- Shifter: `shifterimg pull docker:<ns>/<img>:<tag>` (login node).
- Apptainer: `apptainer pull <img>.sif docker://<ns>/<img>:<tag>`.

## Databases (download on a LOGIN node — compute has no internet)
- KOfam (~5 GB): ko_list + profiles/ from genome.jp.
- UniRef50 (~15 GB): `mmseqs databases UniRef50 uniref50 tmp` (auto-download+format).
- CheckM2 (~3 GB), GTDB-Tk (~100 GB), DRAM (~500 GB) — only if needed.
- Put them on a runtime-mounted filesystem (CFS/scratch), NOT home.
- Reference by absolute path (read in place, not staged).

## Credentials
- NERSC: SFAPI client key in ~/.superfacility (job submission) + sshproxy cert
  ~/.ssh/nersc (data transfer, ~24 h — refresh with sshproxy.sh).
- Plain Slurm clusters: usually just your SSH/login — simpler.

## The run sequence
1. build + pull containers
2. set up databases (login node) on mounted storage
3. put/stage input data (reads on submit host are staged; cluster data is by path)
4. TEST: 1-2 samples, full reads, end to end
5. only after the test completes -> scale to the full dataset
