#!/usr/bin/env python3
"""Stage 1 pipeline: regenerate dummy data, verify it against the answer key,
build golden_results.xlsx, recalculate it in LibreOffice and cross-check it in Python.
Usage: python3 engine/generate_stage1.py   (run from the auditsmart/ root)"""
import pathlib
import subprocess
import sys

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
for step in ["make_gl.py", "verify_stage1.py", "build_golden_workbook.py", "recalc_and_check.py"]:
    print(f"== {step}", flush=True)
    r = subprocess.run([sys.executable, step], cwd=DATA)
    if r.returncode:
        sys.exit(f"FAILED at {step} (exit {r.returncode})")
print("Stage 1 pipeline complete.")
