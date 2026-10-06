"""Scenario format and validation.

LLM output is untrusted, so every generated scenario is validated here before
it is stored or run. Rejections are counted and reported as generation quality.

Scenario shape:
{
  "id": "R5-fee-boundary",
  "requirement_id": "R5",
  "title": "Transfer of exactly 500 is charged a fee",
  "steps": [
    {"type": "api", "method": "POST", "path": "/api/transfer",
     "json": {"from": "alice", "to": "bob", "amount": 500},
     "expect_status": 200, "expect_json": {"ok": true, "fee": 5.0}},
    {"type": "ui", "action": "goto", "value": "/"},
    {"type": "ui", "action": "fill", "selector": "[data-testid=login-user]", "value": "alice"},
    {"type": "ui", "action": "click", "selector": "[data-testid=login-submit]"},
    {"type": "ui", "action": "expect_text", "selector": "[data-testid=login-result]", "value": "Welcome"}
  ]
}
"""
import re

ALLOWED_METHODS = {"GET", "POST"}
ALLOWED_UI_ACTIONS = {"goto", "fill", "click", "expect_text"}
MAX_STEPS = 14
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,60}$")
REQ_RE = re.compile(r"^R\d+$")
SCALARS = (str, int, float, bool, type(None))


def validate_scenario(s) -> list:
    """Return a list of problems; an empty list means the scenario is valid."""
    errors = []
    if not isinstance(s, dict):
        return ["scenario is not an object"]
    if not isinstance(s.get("id"), str) or not ID_RE.match(s["id"]):
        errors.append("bad or missing id")
    if not isinstance(s.get("title"), str) or not s["title"].strip():
        errors.append("missing title")
    if not isinstance(s.get("requirement_id"), str) or not REQ_RE.match(s["requirement_id"]):
        errors.append("requirement_id must look like R3")
    steps = s.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("steps must be a non-empty list")
        return errors
    if len(steps) > MAX_STEPS:
        errors.append(f"too many steps ({len(steps)} > {MAX_STEPS})")
    for i, step in enumerate(steps):
        errors.extend(f"step {i}: {e}" for e in _validate_step(step))
    return errors


def _validate_step(step) -> list:
    if not isinstance(step, dict):
        return ["not an object"]
    kind = step.get("type")
    if kind == "api":
        return _validate_api(step)
    if kind == "ui":
        return _validate_ui(step)
    return [f"unknown type {kind!r}"]


def _validate_api(step) -> list:
    errors = []
    if str(step.get("method", "")).upper() not in ALLOWED_METHODS:
        errors.append("method must be GET or POST")
    path = step.get("path")
    if not isinstance(path, str) or not path.startswith("/api/") or ".." in path:
        errors.append("path must start with /api/")
    if "json" in step and not isinstance(step["json"], dict):
        errors.append("json must be an object")
    status = step.get("expect_status", 200)
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        errors.append("expect_status must be an HTTP status code")
    expect = step.get("expect_json", {})
    if not isinstance(expect, dict) or not all(isinstance(v, SCALARS) for v in expect.values()):
        errors.append("expect_json must be an object of scalar values")
    return errors


def _validate_ui(step) -> list:
    errors = []
    action = step.get("action")
    if action not in ALLOWED_UI_ACTIONS:
        return [f"unknown ui action {action!r}"]
    if action in {"fill", "click", "expect_text"} and not isinstance(step.get("selector"), str):
        errors.append("selector required")
    if action in {"goto", "fill", "expect_text"} and not isinstance(step.get("value"), (str, int, float)):
        errors.append("value required")
    if action == "goto" and not str(step.get("value", "")).startswith("/"):
        errors.append("goto value must be a path starting with /")
    return errors


def validate_all(scenarios) -> tuple:
    """Split into (valid, rejected); rejected items are {"scenario", "errors"}. Duplicate ids are dropped."""
    valid, rejected, seen = [], [], set()
    for s in scenarios:
        errs = validate_scenario(s)
        if not errs and s["id"] in seen:
            errs = ["duplicate id"]
        if errs:
            rejected.append({"scenario": s, "errors": errs})
        else:
            seen.add(s["id"])
            valid.append(s)
    return valid, rejected
