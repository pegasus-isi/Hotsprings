FROM mambaorg/micromamba:1.5.8
RUN micromamba install -y -n base -c bioconda -c conda-forge fastp && micromamba clean -a -y
ENV PATH=/opt/conda/bin:$PATH

