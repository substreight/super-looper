#!/usr/bin/env python3
"""score_eval.py - deterministic scorer for the loop-design behavioral eval.

The skill's own gate. Given the labeled scenarios (the answer key) and a results
file (verdicts a blind agent produced), report per-scenario pass/fail and overall
accuracy, and exit nonzero if accuracy falls below the required minimum. Zero deps.

scenarios.jsonl line: {"id","prompt","expected_verdict","acceptable_verdicts":[...],
                       "must_mention":[...],"notes"}
results.jsonl   line: {"id","verdict","rationale"}

A scenario PASSES if the produced verdict is in {expected_verdict} + acceptable_verdicts
AND (must_mention is empty OR the rationale contains at least one of those concepts).
A scenario with no matching result is MISSING (counts as a fail).

Usage:
    python score_eval.py scenarios.jsonl results.jsonl [--min 0.8] [--baseline baseline.json]
"""
import json
import sys


def _load(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score(scenarios, results):
    by_id = {r.get("id"): r for r in results}
    report = []
    for s in scenarios:
        sid = s["id"]
        acceptable = {v.upper() for v in [s["expected_verdict"], *s.get("acceptable_verdicts", [])]}
        r = by_id.get(sid)
        if r is None:
            report.append((sid, False, "MISSING result"))
            continue
        verdict = str(r.get("verdict", "")).upper().strip()
        verdict_ok = verdict in acceptable
        must = [m.lower() for m in s.get("must_mention", [])]
        rationale = str(r.get("rationale", "")).lower()
        reason_ok = (not must) or any(m in rationale for m in must)
        ok = verdict_ok and reason_ok
        if ok:
            why = "ok"
        elif not verdict_ok:
            why = f"verdict {verdict!r} not in {sorted(acceptable)}"
        else:
            why = "rationale mentions none of: " + ", ".join(must)
        report.append((sid, ok, why))
    return report


def _parse_args(argv):
    rest, args, min_acc, baseline = argv[1:], [], 0.8, None
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--min":
            min_acc = float(rest[i + 1]); i += 2; continue
        if a.startswith("--min="):
            min_acc = float(a.split("=", 1)[1]); i += 1; continue
        if a == "--baseline":
            baseline = rest[i + 1]; i += 2; continue
        if a.startswith("--baseline="):
            baseline = a.split("=", 1)[1]; i += 1; continue
        args.append(a); i += 1
    return args, min_acc, baseline


def _baseline_passing_ids(path):
    """Return the set of scenario ids that passed at the recorded baseline.

    Accepts either an explicit ``passing_ids`` list or, failing that, an empty
    set (so an older baseline without ids simply imposes no per-scenario floor).
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("passing_ids") or [])


def regressions(report, baseline_ids):
    """Scenario ids that passed at baseline but fail now -- the no-regression gate."""
    now_passing = {sid for sid, ok, _ in report if ok}
    return sorted(baseline_ids - now_passing)


def main(argv):
    args, min_acc, baseline = _parse_args(argv)
    if len(args) < 2:
        print(__doc__)
        return 2
    report = score(_load(args[0]), _load(args[1]))
    passed = sum(1 for _, ok, _ in report if ok)
    total = len(report)
    for sid, ok, why in report:
        print(f"{'PASS' if ok else 'FAIL'}  {sid:<20}{'' if ok else '  - ' + why}")
    acc = passed / total if total else 0.0
    print(f"\naccuracy: {passed}/{total} = {acc:.0%}  (min required {min_acc:.0%})")
    failed = False
    if acc < min_acc:
        print("FAILED: below required accuracy - the skill regressed.", file=sys.stderr)
        failed = True
    if baseline:
        regressed = regressions(report, _baseline_passing_ids(baseline))
        if regressed:
            print(
                "FAILED: previously-passing scenario(s) regressed: " + ", ".join(regressed),
                file=sys.stderr,
            )
            failed = True
        else:
            print("no-regression check: OK (no previously-passing scenario regressed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
