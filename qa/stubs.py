"""Canned LLM answers, used ONLY with QA_LLM=stub to test the pipeline plumbing offline.

Nothing here is a model result. Output produced under the stub is stamped
"stub" in every results file and the report prints a warning. Do not quote
numbers from stub runs as evidence of what an LLM can do.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _api(method, path, body=None, status=200, expect=None):
    step = {"type": "api", "method": method, "path": path, "expect_status": status}
    if body is not None:
        step["json"] = body
    if expect:
        step["expect_json"] = expect
    return step


def _login(user, pw, status, expect):
    return _api("POST", "/api/login", {"username": user, "password": pw}, status, expect)


def _transfer(amount, status=200, expect=None, src="alice", dst="bob"):
    return _api("POST", "/api/transfer", {"from": src, "to": dst, "amount": amount}, status, expect)


def _coupon(user, code, total, status, expect):
    return _api("POST", "/api/coupon", {"user": user, "code": code, "total": total}, status, expect)


def _sc(sid, req, title, steps):
    return {"id": sid, "requirement_id": req, "title": title, "steps": steps}


CANNED_SCENARIOS = {
    "R1": [
        _sc("R1-valid-login", "R1", "Valid credentials log in", [_login("alice", "pass123", 200, {"ok": True, "user": "alice"})]),
        _sc("R1-wrong-password", "R1", "Wrong password is rejected", [_login("alice", "nope", 401, {"error": "invalid_credentials"})]),
        _sc("R1-wrong-expectation", "R1", "Unknown user (deliberately wrong expected status)", [_login("ghost", "x", 403, {"error": "invalid_credentials"})]),
    ],
    "R2": [
        _sc("R2-lockout-after-three", "R2", "Locked after 3 failures even with correct password", [
            _login("bob", "x", 401, {"error": "invalid_credentials"}),
            _login("bob", "x", 401, {"error": "invalid_credentials"}),
            _login("bob", "x", 401, {"error": "invalid_credentials"}),
            _login("bob", "pass456", 423, {"error": "account_locked"}),
        ]),
        _sc("R2-success-resets-count", "R2", "Successful login resets failures", [
            _login("bob", "x", 401, None), _login("bob", "x", 401, None),
            _login("bob", "pass456", 200, {"ok": True}),
            _login("bob", "x", 401, None), _login("bob", "x", 401, None),
            _login("bob", "pass456", 200, {"ok": True}),
        ]),
    ],
    "R3": [
        _sc("R3-negative-amount", "R3", "Negative amount rejected", [_transfer(-100, 400, {"error": "invalid_amount"})]),
        _sc("R3-zero-amount", "R3", "Zero amount rejected", [_transfer(0, 400, {"error": "invalid_amount"})]),
    ],
    "R4": [
        _sc("R4-over-balance", "R4", "Amount above balance rejected", [_transfer(1500, 400, {"error": "insufficient_funds"})]),
        _sc("R4-fee-overdraw", "R4", "Full balance plus fee is rejected", [_transfer(1000, 400, {"error": "insufficient_funds"})]),
    ],
    "R5": [
        _sc("R5-below-threshold", "R5", "499 has no fee", [_transfer(499, 200, {"fee": 0.0, "from_balance": 501.0})]),
        _sc("R5-exactly-500", "R5", "500 is charged 5.00", [_transfer(500, 200, {"fee": 5.0, "from_balance": 495.0, "to_balance": 700.0})]),
        _sc("R5-above-threshold", "R5", "600 is charged 6.00", [_transfer(600, 200, {"fee": 6.0, "from_balance": 394.0, "to_balance": 800.0})]),
    ],
    "R6": [
        _sc("R6-save10", "R6", "SAVE10 gives 10% off", [_coupon("alice", "SAVE10", 100, 200, {"discounted_total": 90.0})]),
        _sc("R6-single-use", "R6", "Second use by same user rejected", [
            _coupon("alice", "SAVE10", 100, 200, {"discounted_total": 90.0}),
            _coupon("alice", "SAVE10", 100, 409, {"error": "coupon_already_used"}),
        ]),
        _sc("R6-unknown-code", "R6", "Unknown code is 404", [_coupon("alice", "NOPE", 100, 404, {"error": "invalid_coupon"})]),
    ],
    "R7": [
        _sc("R7-ui-login", "R7", "UI login shows welcome", [
            {"type": "ui", "action": "goto", "value": "/"},
            {"type": "ui", "action": "fill", "selector": "[data-testid=login-user]", "value": "alice"},
            {"type": "ui", "action": "fill", "selector": "[data-testid=login-pass]", "value": "pass123"},
            {"type": "ui", "action": "click", "selector": "[data-testid=login-submit]"},
            {"type": "ui", "action": "expect_text", "selector": "[data-testid=login-result]", "value": "Welcome alice"},
        ]),
        _sc("R7-ui-transfer-fee", "R7", "UI transfer of 600 shows fee 6.00", [
            {"type": "ui", "action": "goto", "value": "/"},
            {"type": "ui", "action": "fill", "selector": "[data-testid=transfer-from]", "value": "alice"},
            {"type": "ui", "action": "fill", "selector": "[data-testid=transfer-to]", "value": "bob"},
            {"type": "ui", "action": "fill", "selector": "[data-testid=transfer-amount]", "value": "600"},
            {"type": "ui", "action": "click", "selector": "[data-testid=transfer-submit]"},
            {"type": "ui", "action": "expect_text", "selector": "[data-testid=transfer-result]", "value": "Transfer OK, fee 6.00"},
        ]),
    ],
}


def _field(prompt, name):
    m = re.search(rf"^{name}: (.+)$", prompt, re.M)
    return m.group(1).strip() if m else ""


def respond(task: str, user: str) -> dict:
    if task == "generate":
        req = _field(user, "REQUIREMENT_ID")
        return {"scenarios": CANNED_SCENARIOS.get(req, [])}
    if task == "triage":
        return _triage(user)
    raise ValueError(task)


def _triage(user: str) -> dict:
    sid, req = _field(user, "SCENARIO_ID"), _field(user, "REQUIREMENT_ID")
    if "wrong-expectation" in sid:
        return {
            "classification": "test_bug",
            "confidence": 0.9,
            "reasoning": "The requirement says unknown users get 401, but the scenario expects 403.",
            "edit": None,
        }
    bugs = json.loads((ROOT / "seeded_bugs.json").read_text())["bugs"]
    for bug in bugs:
        if bug["requirement"] == req:
            return {
                "classification": "product_bug",
                "confidence": 0.85,
                "reasoning": f"Observed behaviour contradicts {req}; see edit.",
                "edit": bug["fix"],
            }
    return {"classification": "unknown", "confidence": 0.2, "reasoning": "No idea.", "edit": None}
