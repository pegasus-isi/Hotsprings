# SubductCR end-to-end workflow — one-command operations
# ------------------------------------------------------
NS ?= swarmourr        # Docker Hub namespace for the images

.PHONY: help containers data prepare check plan run clean

help:
	@echo "SubductCR workflow"
	@echo "  make containers   build + push the container images"
	@echo "  make data                    download & organize all inputs (fresh)"
	@echo "  make prepare INPUT=/path     use existing data, normalize, fetch gaps"
	@echo "  make check   INPUT=/path     report what's present/missing (no changes)"
	@echo "  make plan         build the workflow DAG (no submit)"
	@echo "  make run          plan + submit the workflow"
	@echo ""
	@echo "  backend: export SUBDUCTCR_USE_SIF=1  (ACCESS) or"
	@echo "           export SUBDUCTCR_USE_SHIFTER=1 (Perlmutter);"
	@echo "           default is Docker Hub images."

containers:
	./containers/build.sh $(NS)

data:
	./bin/get_data.sh all

# use your EXISTING data: check what's there, normalize names, download only gaps
prepare:
	./bin/prepare_data.sh $(INPUT)

# report what's present/missing without changing anything
check:
	./bin/prepare_data.sh $(INPUT) --check

plan:
	python3.11 workflow/end_to_end.py --plan-only

run:
	python3.11 workflow/end_to_end.py

clean:
	rm -rf runs/ *.dag* *.log .pegasus* workflow/__pycache__
