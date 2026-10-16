#!/usr/bin/env python3
"""samples_tab: workbook + blank_ref.json + airstd_ref.json -> samples_tab.csv
   (concentrations + ratios)"""
import sys
from gaslib import Context, read_json, samples_overlay, write_overlay_csv

def main(workbook):
    ctx = Context(workbook)
    blank_avg = read_json("blank_ref.json")
    air_avg = read_json("airstd_ref.json")
    ov = samples_overlay(ctx, blank_avg, air_avg)
    write_overlay_csv("samples_tab.csv", ov)
    print(f"samples_tab.csv written ({len(ov)} cells)")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GAS_PROCESS.xlsx")
