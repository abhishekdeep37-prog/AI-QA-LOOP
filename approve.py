#!/usr/bin/env python3
"""Step 4: human review of AI-proposed fixes. The ONLY place a patch is ever applied.

    python approve.py list
    python approve.py show   <scenario_id>
    python approve.py apply  <scenario_id> [--yes]
    python approve.py reject <scenario_id> [reason...]

Every decision is appended to results/decisions.jsonl (used for the "AI fixes merged" metric).
BLOCK-tier proposals cannot be applied. Re-run run_suite.py after applying.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from qa import patching, policy

ROOT = Path(__file__).parent
TRIAGE = ROOT / "results" / "triage.json"
DECISIONS = ROOT / "results" / "decisions.jsonl"


def load_items():
    if not TRIAGE.exists():
        sys.exit("no results/triage.json yet; run triage.py first")
    items = json.loads(TRIAGE.read_text())["items"]
    return [i for i in items if i["status"] in {"proposed", "blocked"}]


def decided():
    out = {}
    if DECISIONS.exists():
        for line in DECISIONS.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                out[d["scenario_id"]] = d
    return out


def record(scenario_id, decision, reason=""):
    DECISIONS.parent.mkdir(exist_ok=True)
    entry = {"scenario_id": scenario_id, "decision": decision, "reason": reason,
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with DECISIONS.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def find(items, sid):
    for i in items:
        if i["scenario_id"] == sid:
            return i
    sys.exit(f"no proposal for {sid!r}; run `python approve.py list`")


def cmd_list(_):
    items, done = load_items(), decided()
    if not items:
        print("no proposals")
    for i in items:
        state = done.get(i["scenario_id"], {}).get("decision", "pending")
        print(f"{i['scenario_id']:28} {i['decision']['tier']:17} conf={i['confidence']:.2f}  [{state}]")
        for reason in i["decision"]["reasons"]:
            print(f"    - {reason}")


def cmd_show(a):
    i = find(load_items(), a.scenario_id)
    print(f"{i['scenario_id']}  ({i['requirement_id']})  {i['classification']}  conf={i['confidence']:.2f}")
    print(f"Reasoning: {i['reasoning']}")
    print(f"Verification: fixed={i['verification']['fixed']} regressions={i['verification']['regressions']}")
    print(f"Policy: {i['decision']['tier']}: {'; '.join(i['decision']['reasons'])}\n")
    print(i["diff"])


def cmd_apply(a):
    i = find(load_items(), a.scenario_id)
    if i["decision"]["tier"] == policy.BLOCK:
        sys.exit(f"refused: this proposal is BLOCKed ({'; '.join(i['decision']['reasons'])})")
    target = ROOT / i["edit"]["file"]
    try:
        patched = patching.apply_edit(target.read_text(), i["edit"]["old"], i["edit"]["new"])
    except patching.PatchError as e:
        sys.exit(f"stale proposal, cannot apply: {e}")
    print(i["diff"])
    if i["decision"]["tier"] == policy.HUMAN_REVIEW:
        print("Needs human review: " + "; ".join(i["decision"]["reasons"]))
    if not a.yes and input("Apply this change? [y/N] ").strip().lower() != "y":
        record(i["scenario_id"], "rejected", "declined at prompt")
        sys.exit("not applied (recorded as rejected)")
    target.write_text(patched)
    record(i["scenario_id"], "accepted")
    print(f"applied to {i['edit']['file']}. Re-run: python run_suite.py")


def cmd_reject(a):
    find(load_items(), a.scenario_id)
    record(a.scenario_id, "rejected", " ".join(a.reason))
    print("recorded as rejected")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("show"); p.add_argument("scenario_id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("apply"); p.add_argument("scenario_id"); p.add_argument("--yes", action="store_true"); p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("reject"); p.add_argument("scenario_id"); p.add_argument("reason", nargs="*"); p.set_defaults(fn=cmd_reject)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
