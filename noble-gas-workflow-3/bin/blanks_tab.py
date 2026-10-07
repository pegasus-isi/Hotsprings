#!/usr/bin/env python3
"""blanks_tab: workbook + blank_ref.json -> blanks_tab.csv (overlay for the avg row)"""
import sys
from gaslib import Context, read_json, blanks_overlay, write_overlay_csv

def main(workbook):
    ctx = Context(workbook)
    blank_avg = read_json("blank_ref.json")
    write_overlay_csv("blanks_tab.csv", blanks_overlay(ctx, blank_avg))
    print("blanks_tab.csv written")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "GAS_PROCESS.xlsx")
