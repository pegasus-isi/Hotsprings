# Site Profiles — one workflow, any HPC system

Pegasus runs the same abstract workflow on any supported HPC. Only the SITE
PROFILE changes: container runtime, scheduler, queues, GPU request, paths.
Adding a system = adding a profile.

## The profile fields
- runtime:   container runtime (shifter | singularity/apptainer | docker)
- cpu_queue: CPU partition name
- gpu_queue: GPU partition name
- gpu_arg:   scheduler GPU request
- cpu_arg:   scheduler CPU constraint (may be empty)
- exec_site: Pegasus execution site name

## NERSC Perlmutter
- runtime: shifter (image = shifter:///<ns>/<img>:<tag>)
- cpu_queue: regular ; gpu_queue: regular
- gpu_arg: "-C gpu" ; cpu_arg: "-C cpu"
- scheduler: Slurm via SFAPI (creds in ~/.superfacility)
- storage: /pscratch (scratch), /global/cfs/cdirs/<proj> (CFS). NOT home.
- containers: `shifterimg pull docker:<ns>/<img>:<tag>` on a login node.

## USC CARC Discovery (a.k.a. "Laguna"-style Slurm)
- runtime: singularity/apptainer (image = file://.../sif/<img>.sif)
- cpu_queue: main ; gpu_queue: gpu
- gpu_arg: "--gres=gpu:a100:1" (or a40/l40s/v100) ; cpu_arg: ""
- scheduler: plain Slurm (simpler than SFAPI)
- GPU: Apptainer needs `--nv` for GPU access
- containers: `apptainer pull sif/<img>.sif docker://<ns>/<img>:<tag>`

## Generic Slurm cluster
- runtime: singularity/apptainer
- cpu_queue / gpu_queue: whatever `sinfo` shows
- gpu_arg: "--gres=gpu:1" (adjust type)
- scheduler: plain Slurm
- check: `sinfo` (partitions), module avail (apptainer/singularity), storage policy

## OLCF Frontier / ALCF Aurora
- runtime: apptainer/singularity
- scheduler: Slurm (Frontier) / PBS (Aurora)
- GPU: AMD (Frontier, ROCm) / Intel (Aurora) — NOT NVIDIA; tool GPU support
  varies, verify per tool
- consult the system's own HPC skill/docs for queue names + storage

## Implementing profiles in the generator
Keep a dict keyed by profile name; select with an env var or argument. The
jobs read queue/gpu_arg/runtime from the active profile. See
templates/pegasus_generator.py for the pattern (SITE dict + SITE[...] in the
transformation helper and the plan call).

## Porting checklist (new system)
1. container runtime? -> set runtime, convert images (pull to .sif if apptainer)
2. scheduler + queues? -> `sinfo`; set cpu_queue/gpu_queue
3. GPU request syntax? -> set gpu_arg; apptainer needs --nv
4. storage the runtime mounts? -> put DBs there (not home); set paths
5. credentials? -> SFAPI vs plain Slurm
6. test 1-2 samples before the full run
