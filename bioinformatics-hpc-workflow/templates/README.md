# Templates

Proven, working patterns from real HPC bioinformatics workflows. Adapt these
rather than generating from scratch.

- pegasus_generator.py  — the generator structure: containers, transformations
  (with SITE profile for portability), replica catalog, the per-sample +
  convergence job wiring, properties. Key patterns:
    * SITE dict (nersc/usc/slurm) -> container runtime, queues, gpu_arg
    * T() helper reads queue + gpu_arg from the active SITE
    * GPU gated by a USE_GPU flag (and gpus param) so CPU-only is one switch
    * per-sample fan-out loop + convergence (merge/predict) once
    * integrity.checking=none so wrapper edits don't need checksum updates
    * worker.package settings so containers without curl still work

- wrapper_patterns.sh  — wrapper conventions:
    * readlink -f on all inputs/outputs (tools cd internally)
    * guard empty inputs (no '>' records) -> write empty output, exit 0
    * SIGPIPE-safe pipes ({ zcat | head || true; } | ...) or seqtk
    * GPU flag only when MAG_GPU=1 (not just non-empty)
    * reference DB path defaults to a CFS/scratch path, not home

- Dockerfile_patterns  — container conventions:
    * CPU tools: micromamba base + bioconda; small, build on a laptop
    * GPU tools: nvidia/cuda base + pytorch-cuda; build on the cluster
    * ALWAYS add curl + wget
    * pin versions; keep images lean (micromamba clean -a -y)

See the gotchas reference for why each convention exists.
