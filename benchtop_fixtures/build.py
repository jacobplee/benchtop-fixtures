"""Build every preset (or the ones named), run the checker, export STEP + STL, write the report.

    python -m benchtop_fixtures.build [preset ...] [--out exports]

Writes <out>/<preset>.step, <out>/<preset>.stl and <out>/report.json. Exits 1 if any preset
is not PASS, so a broken default can never be exported quietly.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import PRESETS, __version__, make
from .check import check, jsonable

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m benchtop_fixtures.build", description=__doc__.split("\n\n")[0])
    ap.add_argument("names", nargs="*", help=f"presets (default: all): {', '.join(PRESETS)}")
    ap.add_argument("--out", default=str(ROOT / "exports"))
    a = ap.parse_args(argv)
    names = a.names or list(PRESETS)
    out = Path(a.out)
    rpath = out / "report.json"
    report = json.loads(rpath.read_text()) if rpath.exists() and a.names else {}
    report.setdefault("presets", {})
    worst = 0
    for n in names:
        t0 = time.time()
        fx = make(n)
        rep = check(fx, n)
        step, stl = fx.export(out, n)
        entry = rep.to_dict()
        entry["files"] = {"step": step.name, "stl": stl.name}
        entry["preset"] = {"part": PRESETS[n][0], "overrides": jsonable(PRESETS[n][1])}
        report["presets"][n] = entry
        print(rep.text() + f"\n  -> {step.name}, {stl.name} ({time.time() - t0:.1f} s)", flush=True)
        worst = max(worst, {"PASS": 0, "FLAG": 1, "FAIL": 1}[rep.verdict])
    report["generator"] = f"benchtop-fixtures {__version__}"
    report["presets"] = {k: report["presets"][k] for k in PRESETS if k in report["presets"]}
    rpath.write_text(json.dumps(report, indent=1) + "\n")
    print(f"wrote {rpath}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
