# AI-driven QA loop: one-page write-up

**Applicant:** Abhishek Deep  **Repo:** [GitHub link]  **Loom:** [link]

Fill every [bracket] from your real run. Delete this line. Keep to ONE page.

## What it does
A local agent loop that turns written requirements into executable tests, runs them with Playwright, triages each failure, proposes a minimal fix, verifies the fix on a copy of the app, and assigns a review tier before anything reaches a human. Nothing is applied without approval. It is tested on a small payments app with 5 seeded bugs so results can be measured against ground truth.

## Architecture
- **Generate:** one LLM call per requirement ([model], run locally with Ollama); output validated against a strict scenario schema.
- **Run:** Playwright API and UI steps; failures retried once, so a pass on retry is reported as flaky rather than as a bug.
- **Triage:** the model classifies each failure (product bug / test bug) with the requirement as source of truth, and proposes a search/replace edit that must match exactly once and compile.
- **Verify:** the edit is applied to a copy of the app and the full suite rerun; any regression blocks it.
- **Policy:** BLOCK / HUMAN_REVIEW / AUTO_PR_ELIGIBLE. Money-path code (transfer, fee, coupon, balance) is always human review; only small, verified, non-money fixes are eligible for an automated PR, and none is auto-merged.
- **Measure:** exact bug-catch numbers from known-correct fixes, plus triage accuracy, patch verification, accepted/rejected fixes and flakiness.

## Results (from my run on [date])
| Metric | Result |
|---|---|
| Seeded bugs caught | [N] of 5 (missed: [ids]) |
| False-positive tests | [N] |
| Triage classification accuracy | [N/M] |
| Scenarios valid / rejected by validation | [N] / [N] |
| Patches proposed / verified on a copy | [N] / [N] |
| AI fixes accepted / rejected | [N] / [N] |
| Flaky scenarios | [N] |

## What broke
1. [Symptom] → [cause] → [what I changed].
2. [Symptom] → [cause] → [what I changed].
3. [Symptom] → [cause] → [what I changed].

## Where autonomy is safe, and where it is not
Safe to automate: running tests, classifying failures, reproducing, and drafting and verifying patches. Needs a human: anything that touches money movement, fees, coupons or balances, any low-confidence patch, and any large diff. A verified patch is still only a proposal.

## Limits
Toy app and a small local model; flakiness detected by one rerun; ground truth maps bugs to the scenarios their fix repairs. At Bolto I would point it at real core flows, triage every red CI build, and open PRs for low-risk fixes behind CI.
