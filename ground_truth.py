#!/usr/bin/env python3
"""Measure which failing scenarios each REAL seeded bug explains.

For every bug in seeded_bugs.json, apply its known-correct fix to a copy of the
app and rerun the suite. Scenarios that flip from failed to passed were caught
because of that bug. Failing scenarios that no real fix repairs are false
positives (bad tests). Run this against the UNPATCHED app, before approve.py.

    python ground_truth.py
"""
import json
from pathlib import Path

from qa import patching

ROOT = Path(__file__).parent


def main():
    run = json.loads((ROOT / "results" / "run.json").read_text())
    scenarios = json.loads((ROOT / "scenarios" / "generated.json").read_text())["scenarios"]
    baseline = {r["id"]: r["status"] for r in run["results"]}
    baseline_steps = {r["id"]: r.get("failed_step_index") for r in run["results"] if r["status"] == "failed"}
    bugs = json.loads((ROOT / "seeded_bugs.json").read_text())["bugs"]
    ui = run["meta"].get("ui", True)

    report, explained = [], set()
    for bug in bugs:
        print(f"[ground-truth] {bug['id']} ...", flush=True)
        fix = bug["fix"]
        ver = patching.verify_patch(ROOT / "app", fix["file"], fix["old"], fix["new"], scenarios, baseline, ui=ui,
                                    baseline_steps=baseline_steps)
        explained.update(ver["progressed"])
        report.append({"id": bug["id"], "requirement": bug["requirement"], "summary": bug["summary"],
                       "caught_by": ver["progressed"], "caught": bool(ver["progressed"]),
                       "fully_fixed_by": ver["fixed"], "fully_fixed": bool(ver["fixed"])})
    failed = {i for i, s in baseline.items() if s == "failed"}
    out = {"bugs": report, "false_positive_scenarios": sorted(failed - explained),
           "definition": "caught = a failing scenario's first failing step passes (or moves later) once the real fix is applied; "
                         "strict = the whole scenario passes"}
    (ROOT / "results" / "ground_truth.json").write_text(json.dumps(out, indent=2) + "\n")
    for b in report:
        print(f"  {b['id']} ({b['requirement']}): {'CAUGHT by ' + ', '.join(b['caught_by']) if b['caught'] else 'MISSED'}"
              f"   [strict, whole scenario passes after fix: {'yes' if b['fully_fixed'] else 'no'}]")
    print(f"  failing scenarios no real bug explains (false positives): {out['false_positive_scenarios']}")


if __name__ == "__main__":
    main()
