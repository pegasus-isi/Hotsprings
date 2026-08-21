# QC image: Trimmomatic + vsearch (used by qc_16s and trim_reads).
# Build for the cluster arch:  docker build --platform linux/amd64 ...
FROM staphb/trimmomatic:0.39
RUN apt-get update && apt-get install -y vsearch && rm -rf /var/lib/apt/lists/*
