#!/usr/bin/env python3
"""Tests for the deterministic scorer's no-regression gate.

Runs under pytest or standalone; needs NO API key. These cover the new
--baseline behavior added for 0.7.0: a previously-passing scenario that fails
must fail the run even when overall accuracy is above --min.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS = os.path.join(ROOT, "evals")
if EVALS not in sys.path:
    sys.path.insert(0, EVALS)

import score_eval as se  # noqa: E402

SCENARIOS = os.path.join(EVALS, "scenarios.jsonl")
SAMPLE = os.path.join(EVALS, "results.sample.jsonl")
BASELINE = os.path.join(EVALS, "baseline.json")


def test_baseline_passing_ids_loaded():
    ids = se._baseline_passing_ids(BASELINE)
    assert "fix-tests" in ids
    assert len(ids) == 10


def test_sample_run_has_no_regressions_against_baseline():
    report = se.score(se._load(SCENARIOS), se._load(SAMPLE))
    assert se.regressions(report, se._baseline_passing_ids(BASELINE)) == []


def test_regressed_scenario_is_detected():
    results = se._load(SAMPLE)
    for r in results:
        if r["id"] == "fix-tests":
            r["verdict"] = "NOT_A_LOOP"
    report = se.score(se._load(SCENARIOS), results)
    assert se.regressions(report, se._baseline_passing_ids(BASELINE)) == ["fix-tests"]


def test_main_exits_nonzero_on_regression_even_above_min():
    results = se._load(SAMPLE)
    for r in results:
        if r["id"] == "fix-tests":
            r["verdict"] = "NOT_A_LOOP"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "regressed.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        rc = se.main(["score_eval.py", SCENARIOS, path, "--min", "0.0", "--baseline", BASELINE])
        assert rc == 1


def test_main_passes_sample_with_baseline():
    rc = se.main(["score_eval.py", SCENARIOS, SAMPLE, "--min", "0.8", "--baseline", BASELINE])
    assert rc == 0


def _run_all():
    fns = sorted((n, fn) for n, fn in globals().items()
                 if n.startswith("test_") and callable(fn))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())
