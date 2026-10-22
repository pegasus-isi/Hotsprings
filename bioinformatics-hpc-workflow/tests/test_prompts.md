# Test Prompts — validate the skill triggers + helps correctly

Run these with the skill loaded; check the response uses the skill's knowledge.

## Tool selection (smart reasoning)
1. "I have 35 metagenome samples, ~1.5 GB reads each, want MAGs and functional
   annotation. I'm on a Slurm cluster with A100 GPUs and 256 GB nodes. What
   tools?"
   EXPECT: reasons from data+resources+goal; picks assembler by memory,
   recommends GPU binners (A100 available), KOfam or MMseqs for annotation,
   states tradeoffs + fallbacks.

2. "Same data but my cluster has no GPUs and I can't build GPU containers."
   EXPECT: switches to MetaBAT2 (CPU), CPU MMseqs/KOfam; notes the GPU gotcha.

## Workflow generation
3. "Build me a Pegasus workflow for metagenome -> MAGs -> KO annotation on
   NERSC Perlmutter."
   EXPECT: generates generator + wrappers + containers with the nersc site
   profile (Shifter, regular queue, -C gpu), per-sample fan-out, convergence.

4. "Port that same workflow to USC CARC."
   EXPECT: changes only the site profile (Apptainer, main/gpu, --gres), not
   the workflow logic.

## Data
5. "How do I get the reads for ENA project PRJNA627197 and organize them?"
   EXPECT: ENA accession->URL, verify mapping, the data/reads layout, sample-
   name consistency warning.

## Gotchas (debugging)
6. "My job exited 141." EXPECT: SIGPIPE; the set -e + pipe fix.
7. "More resources requested than allowed for shared queue." EXPECT: use the
   regular/full queue for multi-core jobs.
8. "KO list not exist /global/homes/.../ko_list but the file is there." EXPECT:
   Shifter doesn't mount home; move DB to CFS/scratch.
9. "CoverM says no sequences in reference FASTA." EXPECT: empty MAGs (valid
   outcome from sparse/subsampled data); guard the step; use full reads.
10. "My metal-gene search returns zero hits." EXPECT: ID mismatch (KO vs
    UniRef); annotate with the matching id type.

## Process
11. "Should I run all 35 samples now?" EXPECT: test 1-2 first, full reads, then
    scale; mention queue-wait reality (1-2 days).

## Composition
12. "What are Perlmutter's exact queue names?" EXPECT: defers to a Perlmutter
    HPC-system skill / docs for system specifics, rather than guessing.
