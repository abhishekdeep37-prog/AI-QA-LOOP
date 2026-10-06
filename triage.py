#!/usr/bin/env python3
"""Step 3: triage every failing scenario, propose a verified fix, and apply the guardrail policy.

For each failure the agent:
  1. classifies it (product_bug / test_bug / unknown) using the requirement as the source of truth,
  2. for product bugs, proposes a minimal search/replace edit,
  3. checks the edit applies exactly once and compiles (one retry with the error fed back),
  4. verifies it on a patched COPY of the app by rerunning the whole suite,
  5. asks qa/policy.py how much human review it needs.

Nothing is applied here. Use approve.py to review and apply.

    python triage.py
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from generate import parse_spec
from qa import llm, patching, policy

ROOT = Path(__file__).parent
APP_FILE = "app/server.py"
CLASSES = {"product_bug", "test_bug", "unknown"}

SYSTEM = (
    "You are a senior engineer triaging a failing automated test. The REQUIREMENT is the source of truth, "
    "not the app and not the test. Decide: product_bug (the app violates the requirement), test_bug (the "
    "test's expectation contradicts the requirement, or uses a wrong endpoint/selector), or unknown. "
    "For a product_bug propose the smallest possible fix as {\"file\", \"old\", \"new\"}: `old` must be copied "
    "EXACTLY from the source (including indentation), must appear once, and `new` is its replacement. "
    "Reply with ONE JSON object: {\"classification\": ..., \"confidence\": 0..1, \"reasoning\": at most "
    "3 sentences, \"edit\": {...} or null}. For test_bug or unknown, edit must be null. "
    "If the failing step uses an endpoint, selector, status code or message that the REQUIREMENT does not state, "
    "or the test expects a value the requirement contradicts, it is a test_bug."
)


def build_prompt(result, scenario, requirement, source, feedback=None):
    parts = [
        f"SCENARIO_ID: {result['id']}",
        f"REQUIREMENT_ID: {result['requirement_id']}",
        "",
        "REQUIREMENT:",
        requirement,
        "",
        "SCENARIO (JSON):",
        json.dumps(scenario, indent=2),
        "",
        f"FAILURE: step {result.get('failed_step_index')} failed ({result.get('error_kind')}).",
        f"Expected: {json.dumps(result.get('expected'))}",
        f"Actual:   {json.dumps(result.get('actual'))}",
        f"Detail:   {result.get('detail', '')}",
        "",
        f"SOURCE of {APP_FILE}:",
        source,
    ]
    if feedback:
        parts += ["", f"Your previous edit was rejected: {feedback}. Reply again with a corrected edit."]
    return "\n".join(parts)


def normalise(reply):
    cls = str(reply.get("classification", "unknown")).strip().lower()
    cls = cls if cls in CLASSES else "unknown"
    try:
        conf = max(0.0, min(1.0, float(reply.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    edit = reply.get("edit")
    if isinstance(edit, dict):
        file = str(edit.get("file", APP_FILE))
        edit = {"file": APP_FILE if Path(file).name == "server.py" else file,
                "old": edit.get("old"), "new": edit.get("new")}
    else:
        edit = None
    return {"classification": cls, "confidence": conf,
            "reasoning": str(reply.get("reasoning", ""))[:600], "edit": edit}


def ask(result, scenario, requirement, source):
    """Return (triage_dict, patched_source_or_None, edit_error_or_None)."""
    feedback = None
    for attempt in range(2):
        prompt = build_prompt(result, scenario, requirement, source, feedback)
        try:
            triage = normalise(llm.chat_json("triage", SYSTEM, prompt))
        except llm.LLMError as e:
            if "Cannot reach Ollama" in str(e):
                raise
            feedback = str(e)
            continue
        if triage["classification"] != "product_bug" or not triage["edit"]:
            return triage, None, None
        try:
            patched = patching.apply_edit(source, triage["edit"]["old"], triage["edit"]["new"])
            return triage, patched, None
        except patching.PatchError as e:
            feedback = str(e)
    return {"classification": "unknown", "confidence": 0.0, "reasoning": "model never produced a usable answer",
            "edit": None}, None, feedback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(ROOT / "results" / "run.json"))
    ap.add_argument("--scenarios", default=str(ROOT / "scenarios" / "generated.json"))
    ap.add_argument("--out", default=str(ROOT / "results" / "triage.json"))
    args = ap.parse_args()

    run = json.loads(Path(args.run).read_text())
    scenarios = json.loads(Path(args.scenarios).read_text())["scenarios"]
    by_id = {s["id"]: s for s in scenarios}
    baseline = {r["id"]: r["status"] for r in run["results"]}
    failed = [r for r in run["results"] if r["status"] == "failed"]
    _, requirements = parse_spec((ROOT / "spec" / "requirements.md").read_text())
    source = (ROOT / APP_FILE).read_text()
    ui = run["meta"].get("ui", True)

    if not failed:
        print("[triage] no failing scenarios; nothing to do")
    items, seen_edits = [], {}
    proposals_dir = ROOT / "results" / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)

    for result in failed:
        sid = result["id"]
        print(f"[triage] {sid} ...", flush=True)
        try:
            triage, patched, edit_error = ask(result, by_id[sid], requirements.get(result["requirement_id"], ""), source)
        except llm.LLMError as e:
            sys.exit(f"error: {e}")
        item = {"scenario_id": sid, "requirement_id": result["requirement_id"], **triage,
                "diff": None, "verification": None, "decision": None, "status": "no_patch", "duplicate_of": None}
        if edit_error:
            item["status"] = "patch_invalid"
            item["decision"] = policy.Decision(policy.BLOCK, [f"edit unusable: {edit_error}"]).to_dict()
        elif patched is not None:
            key = (triage["edit"]["old"], triage["edit"]["new"])
            if key in seen_edits:
                item.update(status="duplicate", duplicate_of=seen_edits[key])
            else:
                seen_edits[key] = sid
                item["diff"] = patching.make_diff(APP_FILE, source, patched)
                print("           verifying patch on a copy of the app ...", flush=True)
                ver = patching.verify_patch(ROOT / "app", APP_FILE, triage["edit"]["old"], triage["edit"]["new"],
                                            scenarios, baseline, ui=ui)
                item["verification"] = ver
                item["decision"] = policy.evaluate(triage["edit"], triage["confidence"], ver, source).to_dict()
                item["status"] = "proposed" if item["decision"]["tier"] != policy.BLOCK else "blocked"
                if item["diff"]:
                    (proposals_dir / f"{sid}.diff").write_text(item["diff"])
        items.append(item)
        tier = item["decision"]["tier"] if item["decision"] else "-"
        print(f"           {item['classification']} (conf {item['confidence']:.2f}) -> {item['status']} [{tier}]")

    doc = {"meta": {**llm.describe(), "triaged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
           "items": items}
    Path(args.out).write_text(json.dumps(doc, indent=2) + "\n")
    print(f"[triage] wrote {args.out}. Next: python approve.py list")


if __name__ == "__main__":
    main()
