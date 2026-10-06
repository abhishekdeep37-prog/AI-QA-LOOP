"""Guardrails: what an AI-proposed fix is allowed to do on its own.

Nothing in this project applies a patch automatically. The policy only decides
how much human attention a verified patch needs:

  BLOCK             never offered for approval (outside allowed files, failed verification, regressions)
  HUMAN_REVIEW      a person must read and approve it (money paths, low confidence, large diffs)
  AUTO_PR_ELIGIBLE  low-risk; could be opened as a PR that still needs green CI

Money-moving code is always HUMAN_REVIEW, whatever the model's confidence.
"""
import re
from dataclasses import dataclass, field

from qa import patching

ALLOWED_FILES = {"app/server.py"}
PROTECTED_FUNCTIONS = {"validate_transfer", "transfer", "calc_fee", "apply_coupon", "coupon"}
PROTECTED_TEXT = re.compile(r"FEE_|COUPON|balance|amount", re.IGNORECASE)
MAX_CHANGED_LINES = 6
MIN_CONFIDENCE = 0.7

BLOCK, HUMAN_REVIEW, AUTO_PR_ELIGIBLE = "BLOCK", "HUMAN_REVIEW", "AUTO_PR_ELIGIBLE"


@dataclass
class Decision:
    tier: str
    reasons: list = field(default_factory=list)

    def to_dict(self):
        return {"tier": self.tier, "reasons": self.reasons}


def evaluate(edit: dict, confidence: float, verification: dict, source: str) -> Decision:
    """Decide the review tier for one verified edit against the current `source` of its file."""
    if edit.get("file") not in ALLOWED_FILES:
        return Decision(BLOCK, [f"file {edit.get('file')!r} is not in the allowed list"])
    if verification["regressions"]:
        return Decision(BLOCK, [f"patch breaks scenarios that passed before: {verification['regressions']}"])
    if not verification["fixed"]:
        return Decision(BLOCK, ["patch did not fix any failing scenario"])

    reasons = []
    start, end = patching.changed_line_range(source, edit["old"])
    touched = patching.enclosing_functions(source, start, end) & PROTECTED_FUNCTIONS
    if touched:
        reasons.append(f"touches money-path function(s): {sorted(touched)}")
    if PROTECTED_TEXT.search(edit["old"]) or PROTECTED_TEXT.search(edit["new"]):
        reasons.append("edit mentions money-related names (fee/coupon/balance/amount)")
    patched = patching.apply_edit(source, edit["old"], edit["new"])
    changed = patching.changed_line_count(source, patched)
    if changed > MAX_CHANGED_LINES:
        reasons.append(f"changes {changed} lines (limit {MAX_CHANGED_LINES})")
    if confidence < MIN_CONFIDENCE:
        reasons.append(f"model confidence {confidence:.2f} is below {MIN_CONFIDENCE}")

    if reasons:
        return Decision(HUMAN_REVIEW, reasons)
    return Decision(AUTO_PR_ELIGIBLE, ["verified, small, outside money paths"])
