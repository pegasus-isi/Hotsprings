---
name: bioinformatics-hpc-workflow
description: Build and run portable bioinformatics workflows on HPC with Pegasus — select tools from requirements and resources, generate the Pegasus workflow + wrappers + containers, target any HPC system (Perlmutter, Frontier, USC CARC, generic Slurm) via site profiles, and avoid the operational gotchas that stall runs. Use when a researcher wants to assemble metagenomes into MAGs, annotate genes, reproduce a bioinformatics pipeline on a cluster, containerize a tool chain, port a workflow between HPC systems, or debug held/failed HPC jobs.
---

# Bioinformatics HPC Workflow Builder

Helps a domain scientist go from "I know the analysis" to "it runs on the
supercomputer" — without weeks of infrastructure pain. The user knows the
biology; this skill supplies the workflow engineering: tool selection,
Pegasus generation, containerization, site portability, and the operational
gotchas that otherwise cost days.

## When this applies

Trigger when the user wants to:
- Turn a bioinformatics analysis into a runnable HPC workflow
- Reproduce or adapt a published pipeline on a cluster
- Assemble metagenomes -> MAGs -> annotation / prediction
- Containerize tools for HPC (Shifter / Apptainer / Singularity)
- Port a workflow between HPC systems
- Understand why an HPC job is held, failed, or slow

NOT for: pure wet-lab questions, interpreting biological results (that's the
scientist's call), or becoming a full HPC sysadmin.

## The process (walk the user through this)

1. **Understand the goal + constraints**: what analysis, what data (reads?
   MAGs? read length/depth), what HPC system, what resources (GPU? memory?),
   what matters (speed vs quality, allocation budget).
1b. **Get + organize the data** (see references/data_acquisition.md) — resolve
   accessions (ENA/SRA) to files, lay them out where the generator expects,
   keep sample IDs consistent across reads/metadata/generator.
2. **Select the tools** (see references/tool_selection.md) — reason from the
   data + resources + goal, give the choice WITH tradeoffs and a fallback.
3. **Design the DAG** — map the tool chain to jobs, inputs, outputs,
   dependencies, per-sample fan-out, and the convergence steps.
4. **Generate the workflow** — a Pegasus generator (templates/), wrapper
   scripts, and container definitions, with a site profile for the target HPC.
5. **Set up the site** — containers, databases, credentials (references/
   site_profiles.md and hpc_setup.md).
6. **Test small, then scale** — always run 1-2 samples first; only scale to
   the full set once the small run completes end to end.
7. **Debug with the gotchas** — when something stalls, consult
   references/gotchas.md before guessing.

## Smart tool selection

Do not hand back a static list. Reason from the user's situation:
- read the data characteristics, resources, and goal
- pick the tool that fits, STATE the tradeoff, and give the fallback if the
  fit is wrong
- let the gotchas steer the choice (e.g. no GPU container infra -> prefer the
  CPU binner; large samples -> avoid the OOM-prone assembler)

references/tool_selection.md holds the decision tables and rules. Apply them
to THIS user's case rather than reciting them.

## Portability (the Pegasus advantage)

The workflow is written once and runs on any HPC system Pegasus supports —
only the SITE PROFILE changes (container runtime, scheduler, queues, GPU
request, paths). references/site_profiles.md gives profiles for NERSC
Perlmutter (Shifter/SFAPI), USC CARC (Apptainer/Slurm), and generic Slurm.
Adding a new system = adding a profile, not rewriting the workflow.

## Compose with HPC-system skills (don't duplicate them)

For system-specific facts (queue names, account flags, modules, storage,
GPU types), defer to a dedicated HPC-system skill when one exists — e.g. the
Genesis hpc-skills (perlmutter, frontier, aurora, slurm, pbs). This skill owns
the portable workflow layer and the site-profile STRUCTURE; the system skill
owns the VALUES for that system. See references/hpc_system_skills.md.

## Test first, always

The single most expensive mistake is scaling to the full dataset before
proving the pipeline. Run 1-2 samples end to end first. Use full reads (not
aggressive subsampling — that starves assembly/binning and produces no MAGs).
Only after the small run completes do you launch the full set.

## The full playbook

references/lessons_learned.md is the end-to-end operational playbook (every
phase: data, build, containers, databases, scheduler, credentials, testing,
debugging) — the narrative behind the quick-lookup gotchas below. Read it when
guiding someone through a whole workflow, not just one error.

## The operational gotchas (consult references/gotchas.md)

These are the failures that cost days if you don't know them:
- shared/small queues cap at a fraction of a node -> use the full/regular
  queue for multi-core jobs
- GPU containers are huge and corrupt laptop Docker -> build them on the
  cluster (podman-hpc) or use CPU builds; CUDA won't resolve on a non-GPU host
- the container must contain curl/wget or the workflow worker package can't
  download inside it
- reference databases must live on a cluster filesystem the container runtime
  mounts (e.g. CFS/scratch), NOT home, which Shifter/Apptainer may not mount
- big databases are read in place by path, never staged per job
- `set -e` + a pipe whose reader closes early (`zcat | head`) dies with
  SIGPIPE (141) -> drop `-e` or absorb the pipe
- a step that can produce nothing (binning on sparse data -> empty MAGs) must
  not crash the downstream job -> guard empty inputs and exit clean
- annotation IDs must match the reference list (KO vs UniRef) or every match
  is empty
- data on the submit host is staged by the workflow manager; data already on
  the cluster is referenced by path — know which

## What to produce

For a new workflow, generate:
- the Pegasus generator (adapt templates/pegasus_generator_complete.py — a
  fully-worked portable generator; or the skeleton for a minimal start)
- the per-step wrapper scripts (templates/wrapper_patterns.sh)
- the container definitions (templates/Dockerfile_patterns)
- the chosen site profile (references/site_profiles.md)
- a test configuration (1-2 samples) and the full configuration

Then guide the user through container build, database setup, the test run,
and scaling.
