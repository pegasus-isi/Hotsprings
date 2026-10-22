# Using Existing HPC System Skills (compose, don't duplicate)

This skill builds the WORKFLOW. For the specifics of each HPC SYSTEM
(scheduler details, queue names, module commands, storage policies), compose
with dedicated HPC-system skills rather than duplicating them.

## The Genesis HPC skills (and similar catalogs)

The Genesis Skills catalog (AI-ModCon/genesis-skills) includes an hpc-skills
group with per-system skills:
- perlmutter   (NERSC)
- frontier     (OLCF)
- aurora       (ALCF)
- slurm        (generic Slurm)
- pbs          (generic PBS)

When present, defer to these for system-level facts: exact partition names,
account flags, module setup, filesystem quotas, GPU types, submission syntax.
This workflow skill supplies the site-profile ABSTRACTION (what fields a
profile needs); the system skill supplies the VALUES for that system.

## Division of labor

| This skill (workflow) | HPC system skill (e.g. perlmutter) |
|-----------------------|------------------------------------|
| tool selection, DAG, containers | queue names, account flags, modules |
| site-profile structure | the system's actual queues/paths |
| Pegasus generation | the scheduler's submission details |
| the gotchas that span systems | the system's quotas/policies |

## How to compose

1. Build the workflow with this skill (tools, DAG, containers, generator).
2. For the target system, pull the values from its HPC-system skill (or its
   docs): container runtime, partitions, GPU request, storage paths, creds.
3. Fill the site profile (references/site_profiles.md) with those values.
4. Run.

If no system skill exists for the target cluster, gather the same facts from
`sinfo` (partitions), `module avail` (apptainer/singularity, tools), the
site's storage docs, and its credential setup — then write the profile.

## Why compose instead of duplicate

System details change (new partitions, new GPU types, policy updates) and are
best maintained by the system's own skill/docs. Duplicating them here would go
stale. This skill stays focused on the portable workflow layer; the system
skills own the system layer. Together they cover the whole problem.
