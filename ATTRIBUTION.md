# Attribution

The `reference_data/` directory vendors data and analysis code from:

> Fullerton, K.M., Schrenk, M.O., Yucel, M. et al. "Effect of tectonic
> processes on biosphere-geosphere feedbacks across a convergent margin."
> Nature Geoscience 14, 301-306 (2021). https://doi.org/10.1038/s41561-021-00725-0

Source repository: https://github.com/dgiovannelli/SubductCR_16S-diversity
Released by the authors under Creative Commons Attribution 4.0 International
(CC BY 4.0): https://creativecommons.org/licenses/by/4.0/

The Pegasus wrapper scripts in `bin/` reimplement the methods of that repository
in a modular, parametrised form so they can be orchestrated as a Pegasus DAG.
They follow the same statistical approach (phyloseq normalisation; Spearman
co-occurrence networks with Louvain community detection; VSURF variable ranking;
vegan NMDS/ADONIS; the Magnabosco cell-integration and carbon-flux equations).

Raw sequences: NCBI SRA BioProject PRJNA579365 (16S) and PRJNA627197 (metagenome).

This orchestration layer is provided for reproducibility. If you use it, cite the
paper above and the Pegasus WMS:
> Deelman, E. et al. "Pegasus, a workflow management system for science
> automation." Future Generation Computer Systems 46, 17-35 (2015).
