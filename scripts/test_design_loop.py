#!/usr/bin/env python3
"""Tests for design_loop.py. Runs under pytest or standalone."""

import copy

import design_loop as d


GOOD_ANSWERS = {
    "task": "Regenerate TypeScript client and keep it compiling",
    "recurs": True,
    "wrong_result_signal": "tsc exits nonzero OR generated client diff is empty",
    "gate_check": "tsc exits 0 AND generated client diff is non-empty",
    "finished_state": "generated client compiles and tsc exits 0",
    "evidence": "tsc exits 0",
    "may_touch": ["src/generated/", "state/progress.jsonl"],
    "must_not_touch": ["src/handwritten/", "production credentials"],
    "budget": {"max_runtime_seconds": 1200},
    "unattended": False,
    "output_reversibility": "reversible",
    "gate_rung": "tool",
    "end_to_end": True,
}


def _answers(**overrides):
    data = copy.deepcopy(GOOD_ANSWERS)
    data.update(overrides)
    return data


def test_unknown_gate_requires_discovery():
    report = d.classify_answers(_answers(wrong_result_signal="unknown", gate_check="unknown", evidence="unknown"))
    assert report["verdict"] == "DISCOVERY_REQUIRED", report
    assert report["autonomy"] == "L0", report
    assert any("automatically prove" in q for q in report["open_questions"]), report


def test_unknown_budget_requires_discovery():
    report = d.classify_answers(_answers(budget="cheap enough"))
    assert report["verdict"] == "DISCOVERY_REQUIRED", report
    assert any("machine-readable" in q for q in report["open_questions"]), report


def test_deterministic_job_uses_scheduler():
    report = d.classify_answers(_answers(deterministic_without_llm=True))
    assert report["verdict"] == "USE_SCHEDULER", report


def test_subjective_gate_is_human_in_loop():
    report = d.classify_answers(_answers(gate_check="the result is good enough", evidence="unknown"))
    assert report["verdict"] == "HUMAN_IN_LOOP", report


def test_good_answers_build_valid_l2_spec():
    spec, report = d.build_spec(_answers())
    assert report["verdict"] == "AUTONOMOUS_LOOP", report
    assert report["validation"]["errors"] == [], report
    assert spec["autonomy"]["requested"] == "L2", spec["autonomy"]


def test_l3_requires_proven_manual_pass():
    spec, report = d.build_spec(_answers(unattended=True))
    assert report["verdict"] == "AUTONOMOUS_LOOP", report
    assert spec["autonomy"]["requested"] == "L2", spec["autonomy"]
    assert "proven_manual_pass" in " ".join(report.get("missing_for_more_autonomy", [])), report


def test_proven_unattended_answers_build_l3_spec():
    spec, report = d.build_spec(_answers(unattended=True, proven_manual_pass=True, proven_cheap=True))
    assert report["validation"]["errors"] == [], report
    assert spec["autonomy"]["requested"] == "L3", spec["autonomy"]


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
    import sys
    sys.exit(_run_all())
