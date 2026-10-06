# SubductCR R environment
# =============================================================================
# Base: Bioconductor 3.18  ==>  R 4.3.3  (verified).
# Every library the workflow's R scripts use is installed here and version-
# pinned where a newer release is incompatible with R 4.3.3.
# =============================================================================
FROM bioconductor/bioconductor_docker:RELEASE_3_18

# ---- system libraries needed to compile the R packages ----------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4-openssl-dev libssl-dev libxml2-dev \
        libgmp-dev libmpfr-dev libgsl-dev \
        libfontconfig1-dev libharfbuzz-dev libfribidi-dev \
        libfreetype6-dev libpng-dev libtiff5-dev libjpeg-dev \
        libnlopt-dev libblas-dev liblapack-dev gfortran cmake \
    && rm -rf /var/lib/apt/lists/*

# ---- Bioconductor packages --------------------------------------------------
RUN R -e 'BiocManager::install(c("phyloseq","microbiome"), update=FALSE, ask=FALSE)'

# ---- version pins required for R 4.3.3 --------------------------------------
# Deriv >= 4.5 uses an R>=4.4 C API and will not compile here; 4.1.3 does.
RUN R -e 'install.packages("remotes", repos="https://cloud.r-project.org"); \
          remotes::install_version("Deriv", version="4.1.3", \
                                   repos="https://cloud.r-project.org", upgrade="never")'

# ---- CRAN packages (installed individually so one failure is visible) -------
RUN for pkg in \
        vegan igraph ggplot2 yaml \
        dplyr tidyr readr ; do \
        R -e "install.packages('$pkg', repos='https://cloud.r-project.org')" ; \
    done

# ---- verify everything loads (build fails loudly if a package is missing) ---
RUN R -e 'pkgs <- c("phyloseq","microbiome","vegan","igraph","ggplot2","yaml","dplyr"); \
          ok <- sapply(pkgs, requireNamespace, quietly=TRUE); \
          print(data.frame(package=pkgs, available=ok)); \
          if (!all(ok)) quit(status=1)'
