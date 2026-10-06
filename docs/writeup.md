# AI-driven QA loop: one-page write-up

**Applicant:** Abhishek Deep  **Repo:** [GitHub link]  **Loom:** [Loom link]

## What it does
A local agent loop that turns written requirements into executable tests, runs them with Playwright, triages each failure, proposes a minimal fix, verifies the fix on a copy of the app, and assigns a review tier before anything reaches a human. Nothing is applied without approval. I tested it on a small payments app with 5 bugs I seeded, so every result can be checked against ground truth. The whole system runs locally (Ollama, llama3.1:8b), with no API keys.

[Edit or delete this line to match how you want to describe your own process: "I designed the loop and built it with AI coding assistance (Claude); I ran every stage, debugged the failures below, and reviewed the proposed patch myself."]

## Architecture
- **Generate:** one LLM call per requirement; every scenario is checked against a strict schema, and unknown selectors, wrong step types and oversized scenarios are rejected, with the reason fed back for a retry.
- **Run:** Playwright API and UI steps; a failure is retried once, so a pass on retry is reported as flaky, not as a bug.
- **Triage:** the model classifies each failure (product bug / test bug) using the requirement as the source of truth, and proposes a search/replace edit that must match the source exactly once and compile.
- **Verify:** the edit is applied to a copy of the app and the whole suite is rerun; a regression blocks it.
- **Policy:** BLOCK / HUMAN_REVIEW / AUTO_PR_ELIGIBLE. Anything touching money paths (transfer, fee, coupon, balance) is always human review. Nothing is auto-merged.
- **Measure:** ground truth applies each known-correct fix to a copy of the app to count which real bugs the generated tests found.

## Results (my run on 6 Oct 2026, llama3.1:8b)
| Metric | Result |
|---|---|
| Scenarios generated (valid / rejected by validator) | 26 / 2 |
| Seeded bugs caught | 3 of 5 (missed: fee overdraw, lockout threshold). Strict (whole scenario passes after the fix): 2 of 5 |
| Failing scenarios with no real bug behind them (false positives) | 15 of 19 failures |
| Triage verdicts | 7 of 19 failures got a verdict (5 product bug, 2 test bug); 12 were "unknown" |
| Of the 5 "product bug" verdicts | 3 were real bugs, 2 were wrong |
| Patches proposed / verified on a copy | 5 / 1 |
| Review tiers | 1 human review, 4 blocked |
| AI fixes accepted by me | 1 (negative-amount validation) |
| Flaky | 0 |

## What broke
1. **First run: every test failed.** The model invented UI selectors that do not exist, and Ollama's default context window silently truncated long prompts. I added a selector allowlist to the validator, API-only prompts for the API requirements, and a larger context window. The second run produced 26 valid scenarios.
2. **My own measurement was wrong.** Rejection reasons were being discarded (it printed "0 rejected" when whole requirements had failed validation), and ground truth only counted a bug as caught if the entire scenario later passed, so it reported 0 of 5. I now keep the rejection reasons, and report both a step-level and a strict number.
3. **Most false positives share one cause.** In 9 of the 15, the model expected a balance as the string "1000.00" while the API returns a number. The spec never stated types. Triage labelled two of these as test bugs, correctly, but most failures got no usable verdict from an 8B model, so only one patch reached verification. I have not fixed this yet.

## Where autonomy is safe, and where it is not
Safe to automate: running tests, classifying failures, reproducing, drafting and verifying patches. Needs a human: anything touching money movement, fees, coupons or balances, any low-confidence patch, and any large diff. A verified patch is still only a proposal. In this run the policy blocked 4 of 5 proposed patches, including 2 wrong "product bug" calls, so a human never saw them.

## Limits and next steps
Toy app; small local model; flakiness is detected by one rerun; ground truth credits a bug when its fix moves a failing step, so it can over-credit. Next: state types in the spec, a stronger model for triage, a second pass that asks the model to check its own test against the requirement before running it, and PRs only for low-risk fixes behind CI. At Bolto I would point this at real core flows and triage every red build.
