"""Run the bundled demo: replay the scripted 15-minute lunch rush and
print the measured results. Writes outputs/report.json, outputs/report.md
and outputs/floor-map.html.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tablemonitor.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["demo", "--output-dir",
                           str(Path(__file__).resolve().parents[1] / "outputs")]))
