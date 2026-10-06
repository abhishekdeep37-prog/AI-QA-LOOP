# Loom script (target 4:30, hard cap 5:00)

Use your own words. These are talking points, not a script to read. Every number must come from YOUR real run (`results/metrics.md`). If a number is bad, say it anyway; "what broke" is a required section.

## Before you hit record

1. Do the full pipeline once with the real model so `scenarios/generated.json`, `results/run.json`, `results/ground_truth.json`, `results/triage.json` and `results/metrics.md` exist.
2. Keep that output. Do not re-run `generate.py` or `triage.py` live: the model is slow and a long wait wastes your five minutes.
3. Live in the video: `run_suite.py`, `approve.py show`, `approve.py apply`, and a re-run. These take seconds.
4. Reset the app before the live part: `git checkout app/server.py`, then `python run_suite.py` once so the failing run is fresh.
5. Open in tabs/windows beforehand: the architecture diagram (README), `spec/requirements.md`, `scenarios/generated.json`, `results/metrics.md`, and a terminal at 18-20pt font.
6. Close Slack/mail, turn on Do Not Disturb, use a clean browser profile. No Rockwell material anywhere on screen.

## Sections

**0:00 – 0:25 Intro**
- Name, one line: "I built a local agent loop that turns requirements into tests, triages failures, proposes fixes and decides how much human review each fix needs."
- Say what it is tested on: a toy payments app with 5 bugs I seeded, so I can measure the system against ground truth.

**0:25 – 1:15 Architecture** (show the README diagram)
- Requirements → LLM generates scenarios (one call per requirement, output validated) → Playwright runs API and UI steps → failures retried once (pass on retry = flaky).
- Triage agent: classifies product bug / test bug, proposes a minimal edit, and the edit must match exactly once and compile.
- Key idea: every patch is verified by rerunning the whole suite on a copy of the app before a person sees it.
- Guardrail policy: BLOCK / HUMAN_REVIEW / AUTO_PR_ELIGIBLE. Money-path code is always human review.
- Everything local: Ollama [model name], no API keys.

**1:15 – 3:00 Live demo**
1. `python run_suite.py` → point at the failures and what each result carries (failing step, expected, actual).
2. Show `results/triage.json` or `python approve.py list` → one money-path proposal (HUMAN_REVIEW with reasons) and one low-risk proposal (AUTO_PR_ELIGIBLE: login lockout threshold).
3. `python approve.py show <id>` → read the diff aloud, say what you are checking as the reviewer.
4. `python approve.py apply <id>` → `python run_suite.py` → that scenario now passes, nothing else regressed.

**3:00 – 3:50 Results** (read from `results/metrics.md`; do not round up)
- Seeded bugs caught: [N] of 5. Name the ones missed and why (e.g. the model never generated that boundary case).
- False-positive tests: [N]. Triage classification accuracy: [N/M].
- Patches proposed [N], verified on a copy [N], accepted [N], rejected [N].
- Generation: [N] scenarios valid, [N] rejected by validation, [N] retries.

**3:50 – 4:30 What broke** (pick 2-3 REAL ones from your runs, in this shape: symptom → cause → what I changed)
- Examples of the kind of thing that happens with a small local model; use only the ones you actually saw:
  - invalid or truncated JSON → added validation, retries and a rejected-scenario count
  - wrong expected values in generated tests (expectation contradicts the spec) → triage must use the requirement as source of truth, not the app
  - `old` text not matching the source exactly → exact-match-once rule plus one retry with the error fed back
  - a patch that fixed its scenario but broke another → regression check on the copy
  - UI selector or timing failures → retry-once flaky classification

**4:30 – 4:50 Close**
- What I would do at Bolto: replace the toy app with your real flows, run triage on every red build, open PRs for AUTO_PR_ELIGIBLE fixes behind CI, and keep anything that moves money behind a human.
- Honest limits: toy app, small model, single-rerun flakiness check, no auto-merge. Then stop.

## Recording checklist

- Loom: screen + camera, 1080p, mic check first.
- Speak slower than feels natural. Short sentences.
- Keep terminal output short: `clear` before each command.
- If you stumble, keep going unless it is a wrong fact. Two takes maximum, then pick the better one.
- After recording: watch once at 1x, check the length is under 5:00, and set sharing to "Anyone with the link". Open the link in an incognito window to confirm it plays.
