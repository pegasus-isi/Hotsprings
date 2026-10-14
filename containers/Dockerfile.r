FROM rocker/r-ver:4.3.3
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev libssl-dev libxml2-dev && rm -rf /var/lib/apt/lists/*
RUN R -e 'install.packages(c("dplyr","tidyr","readr"), repos="https://cloud.r-project.org")'
