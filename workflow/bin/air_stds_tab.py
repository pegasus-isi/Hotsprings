#!/usr/bin/env python3
"""air_stds_tab: workbook + blank_ref.json -> air_stds_tab.csv (blank-corrected + ratios)"""
import sys
from gaslib import Context, read_json, air_stds_overlay, write_overlay_csv

def main(workbook):
    ctx = Context(workbook)
    blank_avg = read_json("blank_ref.json")
    ov = air_stds_overlay(ctx, blank_avg)
    write_overlay_csv("air_stds_tab.csv", ov)
    print(f"air_stds_tab.csv written ({len(ov)} cells)")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GAS_PROCESS.xlsx")
