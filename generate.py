#!/usr/bin/env python3
"""Step 1: turn spec/requirements.md into test scenarios with an LLM.

One model call per requirement (small local models do much better with a
narrow task). Output is validated; invalid scenarios are rejected and counted.

    python generate.py                      # all requirements
    python generate.py --only R5 R6         # subset
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from qa import llm
from qa.scenarios import validate_all

ROOT = Path(__file__).parent
SPEC = ROOT / "spec" / "requirements.md"
OUT = ROOT / "scenarios" / "generated.json"
MAX_ATTEMPTS = 3

SYSTEM = (
    "You are a senior QA engineer writing API and UI test scenarios from a requirements document. "
    "Reply with ONE JSON object only: {\"scenarios\": [...]}. Every expected value must come from the "
    "requirement text, never from guesses about the implementation."
)

SCENARIO_FORMAT = """Scenario format (JSON):
{"id": "R5-fee-boundary", "requirement_id": "R5", "title": "short description",
 "steps": [
  {"type": "api", "method": "POST", "path": "/api/transfer",
   "json": {"from": "alice", "to": "bob", "amount": 500},
   "expect_status": 200, "expect_json": {"ok": true, "fee": 5.0}},
  {"type": "ui", "action": "goto", "value": "/"},
  {"type": "ui", "action": "fill", "selector": "[data-testid=login-user]", "value": "alice"},
  {"type": "ui", "action": "click", "selector": "[data-testid=login-submit]"},
  {"type": "ui", "action": "expect_text", "selector": "[data-testid=login-result]", "value": "Welcome alice"}
 ]}
Rules:
- Each scenario starts from the seed data (state is reset before every scenario).
- "expect_json" only lists fields you are sure about; values are strings, numbers, booleans or null.
- Use only the endpoints and data-testid names from the API overview. Ids must be unique and start with the requirement id.
- Cover the happy path, error cases, and boundary values (just below, exactly at, just above a limit).
- Write 3 to 5 scenarios."""


def parse_spec(text: str) -> tuple:
    """Return (api_overview, {"R1": section_text, ...})."""
    overview, reqs = "", {}
    for block in re.split(r"(?m)^## ", text)[1:]:
        title, _, body = block.partition("\n")
        m = re.match(r"(R\d+)\b", title)
        if m:
            reqs[m.group(1)] = f"## {title}\n{body}".strip()
        elif title.lower().startswith("api"):
            overview = f"## {title}\n{body}".strip()
    return overview, reqs


def build_prompt(req_id: str, overview: str, requirement: str) -> str:
    return f"REQUIREMENT_ID: {req_id}\n\n{overview}\n\n{requirement}\n\n{SCENARIO_FORMAT}\n"


def generate_for(req_id, overview, requirement):
    """Return (valid_scenarios, rejected, attempts_used, error_or_None)."""
    prompt = build_prompt(req_id, overview, requirement)
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            reply = llm.chat_json("generate", SYSTEM, prompt)
        except llm.LLMError as e:
            last_error = str(e)
            if "Cannot reach Ollama" in last_error:
                raise
            continue
        raw = reply.get("scenarios")
        if not isinstance(raw, list):
            last_error = "reply had no 'scenarios' list"
            continue
        for s in raw:  # force the requirement id; models often mislabel it
            if isinstance(s, dict):
                s["requirement_id"] = req_id
        valid, rejected = validate_all(raw)
        if valid:
            return valid, rejected, attempt, None
        last_error = f"all {len(raw)} scenarios were invalid"
    return [], [], MAX_ATTEMPTS, last_error


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="requirement ids, e.g. R5 R6")
    args = ap.parse_args()

    overview, reqs = parse_spec(SPEC.read_text())
    wanted = args.only or sorted(reqs, key=lambda r: int(r[1:]))
    all_valid, all_rejected, per_req = [], [], {}

    for req_id in wanted:
        if req_id not in reqs:
            sys.exit(f"unknown requirement {req_id}")
        print(f"[generate] {req_id} ...", flush=True)
        try:
            valid, rejected, attempts, error = generate_for(req_id, overview, reqs[req_id])
        except llm.LLMError as e:
            sys.exit(f"error: {e}")
        ids = {s["id"] for s in all_valid}
        for s in valid:  # keep ids unique across requirements
            if s["id"] in ids:
                s["id"] = f"{s['id']}-{req_id.lower()}"
        all_valid.extend(valid)
        all_rejected.extend(rejected)
        per_req[req_id] = {"valid": len(valid), "rejected": len(rejected), "attempts": attempts, "error": error}
        print(f"           valid={len(valid)} rejected={len(rejected)} attempts={attempts}" + (f" error={error}" if error else ""))

    doc = {
        "meta": {**llm.describe(), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "spec": str(SPEC.relative_to(ROOT))},
        "stats": {"valid": len(all_valid), "rejected": len(all_rejected), "per_requirement": per_req},
        "rejected": all_rejected,
        "scenarios": all_valid,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"[generate] wrote {len(all_valid)} scenarios to {OUT.relative_to(ROOT)} ({len(all_rejected)} rejected)")


if __name__ == "__main__":
    main()
