.PHONY: help images sif catalogs plan plan-sif run dag test-analysis clean
help:
	@echo "make reproduce     # reproduce the paper from the authors\x27 tables (no reads)"
	@echo "make all           # fetch inputs -> build .sif -> plan + submit (one shot)"
	@echo "make fetch         # download + stage all input data into input/"
	@echo "make images        # build + push the 4 Docker images to Docker Hub (swarmourr)"
	@echo "make sif           # build .sif from the Hub images into containers/sif/ (Route A)"
	@echo "make catalogs      # write properties + site/replica/transformation catalogs + workflow.yml"
	@echo "make plan          # plan + submit using Docker images"
	@echo "make plan-only     # plan into an executable workflow but do NOT submit"
	@echo "make plan-sif      # plan + submit using local .sif files (SUBDUCTCR_USE_SIF=1)"
	@echo "make dag           # render the DAG (PDF + PNG) via Graphviz"
	@echo "make test-analysis # run the R analysis stages on the published tables (no reads)"
	@echo "make clean         # remove generated catalogs, work/, output/"

reproduce:
	SUBDUCTCR_USE_SIF=1 python3 reproduce_workflow.py

all:
	./run_all.sh

fetch:
	./fetch_inputs.sh

images:
	./containers/build_and_push.sh swarmourr

sif:
	./containers/build_sif.sh swarmourr

plan-sif:
	SUBDUCTCR_USE_SIF=1 python3 subductcr_workflow.py

plan-only:
	python3 subductcr_workflow.py --plan-only

catalogs:
	python3 subductcr_workflow.py --no-run

plan:
	python3 subductcr_workflow.py

dag:
	python3 gen_dag.py && echo "wrote subductcr_dag.pdf / .png"

# Exercise the analysis half of the DAG on the authors' published tables.
test-analysis:
	@echo ">> filter_normalize + network + geochem on reference_data/"
	bin/gene_merge reference_data/mi-faser_metagenomes/*_mifaser.csv gene_table.tsv 2>/dev/null || \
	  echo "   (supply per-sample mifaser tables, or use mifaser_dataset.csv directly)"
	@echo "   see reference_data/ for the published count tables"

clean:
	rm -rf work output *.yml properties transformations.yml replicas.yml sites.yml \
	       subductcr_dag.* *.dot workflow.yml
