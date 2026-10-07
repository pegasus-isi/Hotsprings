#!/usr/bin/env python3
"""
noble_gas_workflow.py  --  Pegasus 5 abstract workflow (DAG) generator.
Writes noble-gas-reduction.yml + pegasus.properties. Does not plan or run.

ONE input  : input/GAS_PROCESS.xlsx (read by every job)
PARALLEL   : blanks_tab / air_stds_tab / samples_tab fan out and run concurrently
ONE output : GAS_PROCESS_reproduced.xlsx (a single workbook with all tabs)
"""
from pathlib import Path
from Pegasus.api import (
    Workflow, Job, File, Transformation,
    ReplicaCatalog, TransformationCatalog, Properties,
)

BASE = Path(__file__).parent.resolve()
BIN = BASE / "bin"
INPUT = BASE / "input"

# 1. properties
props = Properties()
props["pegasus.mode"] = "development"
props.write()

# 2. replica catalog -- the single input workbook
rc = ReplicaCatalog()
workbook = File("GAS_PROCESS.xlsx")
rc.add_replica("local", workbook, (INPUT / "GAS_PROCESS.xlsx").as_uri())

# 3. transformation catalog -- one executable per job (+ the shared library)
tc = TransformationCatalog()
gaslib = File("gaslib.py")
rc.add_replica("local", gaslib, (BIN / "gaslib.py").as_uri())   # staged beside each job

STEPS = ["build_semiraw", "compute_references",
         "blanks_tab", "air_stds_tab", "samples_tab", "assemble_workbook"]
xf = {}
for step in STEPS:
    t = Transformation(step, site="local", pfn=(BIN / f"{step}.py").as_uri(),
                       is_stageable=True)
    xf[step] = t
    tc.add_transformations(t)

# 4. workflow
wf = Workflow("noble-gas-reduction")

semi_raw   = File("semi_raw.csv")
blanks     = File("blanks.csv")
air_stds   = File("air_stds.csv")
samples    = File("samples.csv")
blank_ref  = File("blank_ref.json")
airstd_ref = File("airstd_ref.json")
blanks_tab   = File("blanks_tab.csv")
air_stds_tab = File("air_stds_tab.csv")
samples_tab  = File("samples_tab.csv")
final_wb     = File("GAS_PROCESS_reproduced.xlsx")

j_semi = (Job(xf["build_semiraw"]).add_args(workbook)
          .add_inputs(workbook, gaslib)
          .add_outputs(semi_raw, blanks, air_stds, samples, stage_out=True))

j_ref = (Job(xf["compute_references"]).add_args(workbook)
         .add_inputs(workbook, gaslib, blanks, air_stds)
         .add_outputs(blank_ref, airstd_ref, stage_out=True))

j_blanks = (Job(xf["blanks_tab"]).add_args(workbook)
            .add_inputs(workbook, gaslib, blanks, blank_ref)
            .add_outputs(blanks_tab, stage_out=True))

j_air = (Job(xf["air_stds_tab"]).add_args(workbook)
         .add_inputs(workbook, gaslib, air_stds, blank_ref)
         .add_outputs(air_stds_tab, stage_out=True))

j_samp = (Job(xf["samples_tab"]).add_args(workbook)
          .add_inputs(workbook, gaslib, samples, blank_ref, airstd_ref)
          .add_outputs(samples_tab, stage_out=True))

j_asm = (Job(xf["assemble_workbook"]).add_args(workbook)
         .add_inputs(workbook, gaslib, semi_raw, blanks_tab, air_stds_tab, samples_tab)
         .add_outputs(final_wb, stage_out=True, register_replica=True))

wf.add_jobs(j_semi, j_ref, j_blanks, j_air, j_samp, j_asm)
wf.add_replica_catalog(rc)
wf.add_transformation_catalog(tc)

# Dependencies inferred from the shared files:
#   build_semiraw -> compute_references -> {blanks_tab, air_stds_tab, samples_tab} -> assemble
wf.write("noble-gas-reduction.yml")
print("wrote noble-gas-reduction.yml and pegasus.properties")
