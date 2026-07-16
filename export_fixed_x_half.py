# export_fixed_x_half.py
# Helper script to run cross_section_plot.py with a fixed X=0.5 ratio and export PNG+SVG

import sys
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent / "cross_section_plot.py"
if not SCRIPT.exists():
    print("cross_section_plot.py not found in repo root. Pull latest commits first.")
    sys.exit(1)

cmd = [sys.executable, str(SCRIPT), "--out", "fixed_x_half", "--svg", "--dpi", "1200", "--width", "16.0", "--ratio", "0.5"]
print("Running:", " ".join(cmd))
res = subprocess.run(cmd)
if res.returncode == 0:
    print("Export complete. Files: fixed_x_half.png, fixed_x_half.svg (repo root)")
else:
    print("Export failed. See above output for errors.")
