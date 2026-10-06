"""Unit tests for the parts that must never be wrong: scenario validation, patch handling, release policy."""
from pathlib import Path

import pytest

from qa import patching, policy
from qa.scenarios import validate_all, validate_scenario

APP_SOURCE = (Path(__file__).parent.parent / "app" / "server.py").read_text()

GOOD = {
    "id": "R5-fee-boundary", "requirement_id": "R5", "title": "fee at 500",
    "steps": [{"type": "api", "method": "POST", "path": "/api/transfer",
               "json": {"from": "alice", "to": "bob", "amount": 500},
               "expect_status": 200, "expect_json": {"ok": True, "fee": 5.0}}],
}
OK_VERIFICATION = {"fixed": ["x"], "regressions": [], "still_failing": []}


def scenario(**overrides):
    return {**GOOD, **overrides}


# ---- scenario validation -------------------------------------------------

def test_valid_scenario_passes():
    assert validate_scenario(GOOD) == []


@pytest.mark.parametrize("path", ["http://evil.example/steal", "/admin", "/api/../etc/passwd"])
def test_api_path_must_stay_inside_the_app(path):
    step = {**GOOD["steps"][0], "path": path}
    assert validate_scenario(scenario(steps=[step]))


def test_unknown_step_type_and_ui_action_rejected():
    assert validate_scenario(scenario(steps=[{"type": "shell", "cmd": "rm -rf /"}]))
    assert validate_scenario(scenario(steps=[{"type": "ui", "action": "eval", "value": "x"}]))


def test_duplicate_ids_are_dropped():
    valid, rejected = validate_all([GOOD, GOOD])
    assert len(valid) == 1 and rejected[0]["errors"] == ["duplicate id"]


def test_too_many_steps_rejected():
    assert validate_scenario(scenario(steps=[GOOD["steps"][0]] * 20))


# ---- patch handling ------------------------------------------------------

def test_edit_must_match_exactly_once():
    with pytest.raises(patching.PatchError):
        patching.apply_edit(APP_SOURCE, "this text is not in the file", "x")
    with pytest.raises(patching.PatchError):
        patching.apply_edit(APP_SOURCE, "return", "return")  # appears many times


def test_edit_must_compile():
    with pytest.raises(patching.PatchError, match="does not compile"):
        patching.apply_edit(APP_SOURCE, "MAX_FAILED_LOGINS = 5", "MAX_FAILED_LOGINS = (")


def test_enclosing_function_detection():
    old = "if amount > FEE_THRESHOLD:"
    start, end = patching.changed_line_range(APP_SOURCE, old)
    assert patching.enclosing_functions(APP_SOURCE, start, end) == {"calc_fee"}


# ---- release policy ------------------------------------------------------

def edit(old, new, file="app/server.py"):
    return {"file": file, "old": old, "new": new}


def test_money_path_always_needs_a_human_even_at_full_confidence():
    d = policy.evaluate(edit("if amount > FEE_THRESHOLD:", "if amount >= FEE_THRESHOLD:"), 1.0, OK_VERIFICATION, APP_SOURCE)
    assert d.tier == policy.HUMAN_REVIEW


def test_small_verified_non_money_fix_is_auto_pr_eligible():
    d = policy.evaluate(edit("MAX_FAILED_LOGINS = 5", "MAX_FAILED_LOGINS = 3"), 0.9, OK_VERIFICATION, APP_SOURCE)
    assert d.tier == policy.AUTO_PR_ELIGIBLE


def test_low_confidence_downgrades_to_human_review():
    d = policy.evaluate(edit("MAX_FAILED_LOGINS = 5", "MAX_FAILED_LOGINS = 3"), 0.4, OK_VERIFICATION, APP_SOURCE)
    assert d.tier == policy.HUMAN_REVIEW


def test_regressions_block_the_patch():
    ver = {"fixed": ["x"], "regressions": ["y"], "still_failing": []}
    d = policy.evaluate(edit("MAX_FAILED_LOGINS = 5", "MAX_FAILED_LOGINS = 3"), 0.9, ver, APP_SOURCE)
    assert d.tier == policy.BLOCK


def test_patch_that_fixes_nothing_is_blocked():
    ver = {"fixed": [], "regressions": [], "still_failing": ["x"]}
    d = policy.evaluate(edit("MAX_FAILED_LOGINS = 5", "MAX_FAILED_LOGINS = 3"), 0.9, ver, APP_SOURCE)
    assert d.tier == policy.BLOCK


def test_files_outside_the_allowlist_are_blocked():
    d = policy.evaluate(edit("a", "b", file=".github/workflows/qa.yml"), 0.9, OK_VERIFICATION, APP_SOURCE)
    assert d.tier == policy.BLOCK
