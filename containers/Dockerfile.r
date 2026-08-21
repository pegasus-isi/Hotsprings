# R analysis container: phyloseq, vegan, igraph, VSURF, missForest, ggplot2, yaml
FROM bioconductor/bioconductor_docker:RELEASE_3_18
RUN R -e 'BiocManager::install(c("phyloseq"), update=FALSE, ask=FALSE)' && \
    R -e 'install.packages(c("vegan","igraph","VSURF","missForest","ggplot2","dplyr","yaml"), repos="https://cloud.r-project.org")'
