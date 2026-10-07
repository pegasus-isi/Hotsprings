#!/usr/bin/env python3
"""build_semiraw: GAS_PROCESS.xlsx -> semi_raw.csv + blanks/air_stds/samples.csv"""
import sys
from gaslib import Context, write_rows_csv

def main(workbook):
    ctx = Context(workbook)
    write_rows_csv("semi_raw.csv", ctx.rows, ctx.join_cols)
    write_rows_csv("blanks.csv", ctx.blanks, ctx.join_cols)
    write_rows_csv("air_stds.csv", ctx.airs, ctx.join_cols)
    write_rows_csv("samples.csv", ctx.samps, ctx.join_cols)
    print(f"semi_raw={len(ctx.rows)} blanks={len(ctx.blanks)} "
          f"air_stds={len(ctx.airs)} samples={len(ctx.samps)}")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GAS_PROCESS.xlsx")
