# ai-qa-loop

A small, honest prototype of an AI-driven QA loop: **requirements → generated tests → run → triage failures → propose a fix → verify it → human approval → metrics.**

It runs fully local (Ollama, no API keys) against a toy payments app with 5 seeded bugs, so every number it reports can be checked against ground truth.

## How it works

```
spec/requirements.md
        │  generate.py   (LLM, one call per requirement, output validated)
        ▼
scenarios/generated.json ──► run_suite.py  (Playwright: API + UI steps, failures retried once)
                                   │
                                   ▼  results/run.json   (passed / failed / flaky + evidence)
                              triage.py
                                   │  1. LLM classifies: product_bug / test_bug / unknown
                                   │  2. LLM proposes {file, old, new}
                                   │  3. edit must match exactly once and compile
                                   │  4. verified on a COPY of the app: full suite rerun
                                   │  5. policy.py picks a review tier
                                   ▼
                  BLOCK │ HUMAN_REVIEW │ AUTO_PR_ELIGIBLE
                                   │
                              approve.py   ← the ONLY place a patch is applied (human y/N)
                                   │
                              report.py   → bugs caught, false positives, flaky, fixes accepted
```

### Guardrails (`qa/policy.py`)

| Tier | When | What it means |
|---|---|---|
| `BLOCK` | file outside allowlist, patch breaks a passing scenario, or fixes nothing | never offered for approval |
| `HUMAN_REVIEW` | touches money-path code (transfer, fee, coupon, balance), low model confidence, or large diff | a person must read it |
| `AUTO_PR_ELIGIBLE` | verified, tiny, outside money paths | could open a PR that still needs green CI |

Nothing is ever applied automatically in this prototype. Money-moving code is always `HUMAN_REVIEW`, even at 100% model confidence.

### Measurement

`ground_truth.py` applies each *known-correct* fix (from `seeded_bugs.json`, which the agents never read) to a copy of the app and checks which failing scenarios flip to passing. That gives exact numbers for bugs caught, bugs missed, and false-positive tests. `report.py` adds triage accuracy, patch verification, review tiers, accepted/rejected fixes and flaky count.

## Run it (macOS)

```bash
cd ai-qa-loop
git init && git add -A && git commit -m "baseline"     # so you can reset the app between runs
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

ollama serve            # in another terminal, if not already running
ollama pull llama3.1:8b

python -m pytest tests -q        # unit tests, no LLM needed

python generate.py               # LLM writes scenarios       -> scenarios/generated.json
python run_suite.py              # run them                   -> results/run.json
python ground_truth.py           # which real bugs were caught (run BEFORE approving fixes)
python triage.py                 # classify, propose, verify  -> results/triage.json
python approve.py list
python approve.py show  <scenario_id>
python approve.py apply <scenario_id>      # human decision
python run_suite.py              # re-run to see the effect
python report.py                 # metrics table             -> results/metrics.md
```

To reset between takes: `git checkout app/server.py && rm -f results/*.json results/decisions.jsonl && rm -rf results/proposals`.

Useful flags: `run_suite.py --no-ui` (API only), `--headed` (watch the browser). Set `QA_MODEL` to try another Ollama model.

## Offline pipeline check (not a demo)

`QA_LLM=stub python generate.py` etc. uses canned answers to test the plumbing without a model. Everything it produces is stamped `stub` and `report.py` prints a warning. Never quote stub numbers as results.

## Known limitations

- The app under test is a toy, with in-memory state and no auth on transfers.
- Small local models make mistakes: invalid JSON, wrong expected values, patches that do not match the source. Those are counted (rejected scenarios, retries, failed verification), not hidden.
- Ground truth maps a bug to the scenarios its fix repairs. A scenario that fails for a *different* reason but also happens to be fixed by a real bug fix would be counted as caught.
- Flakiness is detected by a single rerun. It does not diagnose causes.
- CI runs the committed scenarios without an LLM. Generation and triage run locally.
- Auto-merge is deliberately not implemented.

## Layout

```
app/server.py          system under test (Flask)
spec/requirements.md   source of truth for generation and triage
seeded_bugs.json       ground truth (agents never read it)
qa/                    runner, scenario validation, LLM client, patching, policy
generate.py run_suite.py triage.py approve.py ground_truth.py report.py
tests/                 unit tests for validation, patch safety and policy
.github/workflows/     CI
docs/                  Loom script and write-up template
```
