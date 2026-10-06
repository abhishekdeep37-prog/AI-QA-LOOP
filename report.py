#!/usr/bin/env python3
"""Step 5: measurement. Reads results/*.json and prints/writes a metrics report.

Run ground_truth.py first (against the unpatched app) for exact bug-catch numbers.

    python report.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent
R = ROOT / "results"


def load(path, default=None):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def main():
    gen = load(ROOT / "scenarios" / "generated.json")
    run = load(R / "run.json")
    triage = load(R / "triage.json", {"items": [], "meta": {}})
    truth = load(R / "ground_truth.json")
    seeded = load(ROOT / "seeded_bugs.json")["bugs"]
    decisions = {}
    if (R / "decisions.jsonl").exists():
        for line in (R / "decisions.jsonl").read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                decisions[d["scenario_id"]] = d["decision"]
    if not gen or not run:
        raise SystemExit("need scenarios/generated.json and results/run.json; run generate.py and run_suite.py")

    m = {}
    stub = "stub" in {gen["meta"].get("provider"), triage["meta"].get("provider")}
    m["llm"] = gen["meta"]
    m["generation"] = {"valid": gen["stats"]["valid"], "rejected": gen["stats"]["rejected"],
                       "retries": sum(max(0, v["attempts"] - 1) for v in gen["stats"]["per_requirement"].values())}
    counts = run["counts"]
    m["suite"] = {**counts, "total": len(run["results"])}

    if truth:
        caught = [b for b in truth["bugs"] if b["caught"]]
        m["bugs"] = {"seeded": len(seeded), "caught": len(caught),
                     "missed": [b["id"] for b in truth["bugs"] if not b["caught"]],
                     "false_positive_scenarios": truth["false_positive_scenarios"]}
        explained = {i for b in truth["bugs"] for i in b["caught_by"]}
    else:
        m["bugs"] = {"note": "run ground_truth.py for exact numbers"}
        explained = None

    items = triage["items"]
    canon = [i for i in items if i["status"] in {"proposed", "blocked"}]
    tri = {"failures_triaged": len(items),
           "classified": {c: sum(1 for i in items if i["classification"] == c) for c in ("product_bug", "test_bug", "unknown")}}
    if explained is not None and items:
        correct = sum(1 for i in items if (i["classification"] == "product_bug") == (i["scenario_id"] in explained))
        tri["classification_accuracy"] = f"{correct}/{len(items)}"
    m["triage"] = tri

    verified = [i for i in canon if i["verification"] and i["verification"]["fixed"] and not i["verification"]["regressions"]]
    tiers = {}
    for i in canon:
        tiers[i["decision"]["tier"]] = tiers.get(i["decision"]["tier"], 0) + 1
    accepted = sum(1 for i in canon if decisions.get(i["scenario_id"]) == "accepted")
    rejected = sum(1 for i in canon if decisions.get(i["scenario_id"]) == "rejected")
    m["patches"] = {"proposed": len(canon), "verified_on_copy": len(verified), "by_tier": tiers,
                    "accepted": accepted, "rejected": rejected,
                    "pending": len(canon) - accepted - rejected,
                    "merge_rate": f"{accepted}/{len(canon)}" if canon else "n/a"}

    (R / "metrics.json").write_text(json.dumps(m, indent=2) + "\n")
    lines = ["# QA loop metrics", ""]
    if stub:
        lines += ["> WARNING: produced with the STUB LLM (canned answers). Plumbing test only; not evidence of model quality.", ""]
    lines += [f"Model: {m['llm'].get('provider')} / {m['llm'].get('model')}", "",
              "| Metric | Value |", "|---|---|",
              f"| Scenarios generated (valid / rejected) | {m['generation']['valid']} / {m['generation']['rejected']} (retries: {m['generation']['retries']}) |",
              f"| Suite result | {', '.join(f'{k}={v}' for k, v in m['suite'].items())} |"]
    if "seeded" in m["bugs"]:
        lines += [f"| Seeded bugs caught | {m['bugs']['caught']} of {m['bugs']['seeded']} (missed: {', '.join(m['bugs']['missed']) or 'none'}) |",
                  f"| False-positive scenarios (failing, no real bug) | {len(m['bugs']['false_positive_scenarios'])} {m['bugs']['false_positive_scenarios']} |"]
    else:
        lines.append(f"| Seeded bugs caught | {m['bugs']['note']} |")
    lines += [f"| Failures triaged / classification | {tri['failures_triaged']} / {tri['classified']}"
              + (f", accuracy {tri['classification_accuracy']}" if "classification_accuracy" in tri else "") + " |",
              f"| Patches proposed / verified on a copy | {m['patches']['proposed']} / {m['patches']['verified_on_copy']} |",
              f"| Review tiers | {m['patches']['by_tier']} |",
              f"| AI fixes accepted / rejected / pending | {accepted} / {rejected} / {m['patches']['pending']} |",
              f"| Flaky scenarios | {counts.get('flaky', 0)} |"]
    text = "\n".join(lines) + "\n"
    (R / "metrics.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
