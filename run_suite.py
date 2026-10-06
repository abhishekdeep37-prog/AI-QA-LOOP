#!/usr/bin/env python3
"""Step 2: run the scenarios against the app and write results/run.json.

Failures are retried once; a scenario that fails then passes is "flaky", not a bug.
Exit code is 1 if any scenario still fails, so CI goes red.

    python run_suite.py                 # API + UI scenarios
    python run_suite.py --no-ui         # API only (no browser needed)
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from qa.runner import run_scenarios
from qa.server_ctl import running_server

ROOT = Path(__file__).parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=str(ROOT / "scenarios" / "generated.json"))
    ap.add_argument("--app-dir", default=str(ROOT / "app"))
    ap.add_argument("--out", default=str(ROOT / "results" / "run.json"))
    ap.add_argument("--no-ui", action="store_true")
    ap.add_argument("--headed", action="store_true", help="show the browser (useful while recording)")
    args = ap.parse_args()

    doc = json.loads(Path(args.scenarios).read_text())
    scenarios = doc["scenarios"]
    with running_server(args.app_dir) as url:
        results = run_scenarios(scenarios, url, ui=not args.no_ui, headless=not args.headed)

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    out = {
        "meta": {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "ui": not args.no_ui, "scenario_source": doc.get("meta", {})},
        "counts": counts,
        "results": results,
    }
    Path(args.out).parent.mkdir(exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")

    for r in results:
        line = f"{r['status'].upper():8} {r['id']}"
        if r["status"] in {"failed", "flaky"}:
            line += f"   (step {r.get('failed_step_index')}: expected {r.get('expected')}, got {r.get('actual')})"
        print(line)
    print(f"\n{counts}")
    sys.exit(1 if counts.get("failed") else 0)


if __name__ == "__main__":
    main()
