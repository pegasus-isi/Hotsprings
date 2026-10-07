#!/usr/bin/env python3
"""compute_references: workbook (+ blanks/air_stds) -> blank_ref.json + airstd_ref.json"""
import sys
from gaslib import Context, write_json

def main(workbook):
    ctx = Context(workbook)
    write_json("blank_ref.json", ctx.blank_averages())    # {beam: blank average}
    write_json("airstd_ref.json", ctx.air_averages())     # {beam: air-std bracket average}
    print(f"blank_ref={len(ctx.blank_averages())} airstd_ref={len(ctx.air_averages())}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GAS_PROCESS.xlsx")
