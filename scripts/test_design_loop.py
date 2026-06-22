#!/usr/bin/env python3
"""Tests for design_loop.py. Runs under pytest or standalone."""

import copy
import json
import os

import design_loop as d

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "examples")


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


def test_headroom_case_study_builds_clean_l2_spec():
    with open(os.path.join(EXAMPLES, "headroom-ast-compression.answers.json"), encoding="utf-8") as f:
        answers = json.load(f)
    spec, report = d.build_spec(answers)
    assert report["verdict"] == "AUTONOMOUS_LOOP", report
    assert report["validation"]["errors"] == [], report
    assert report["validation"]["warnings"] == [], report
    assert spec["autonomy"]["requested"] == "L2", spec["autonomy"]


# ---- Fix 1.3: a vacuous gate is treated like "I don't know", not minted into a loop ----

def test_vacuous_gate_requires_discovery():
    # "it works" is grammatical but names no measurable signal and no explicit checker.
    report = d.classify_answers(_answers(gate_check="it works", gate_rung=None))
    assert report["verdict"] == "DISCOVERY_REQUIRED", report


def test_measurable_gate_without_explicit_rung_still_autonomous():
    # Regression guard: a concrete, machine-decidable gate still qualifies without an explicit rung.
    report = d.classify_answers(_answers(gate_check="pytest exits 0 and coverage >= 90", gate_rung=None))
    assert report["verdict"] == "AUTONOMOUS_LOOP", report


# ---- Fix 1.4: end_to_end is not fabricated; L3 needs an explicit attestation ----

def test_end_to_end_not_fabricated_when_absent():
    answers = _answers(unattended=True, proven_manual_pass=True, proven_cheap=True)
    answers.pop("end_to_end", None)
    spec, report = d.build_spec(answers)
    assert spec["verifier"]["end_to_end"] is not True, spec["verifier"]
    assert spec["autonomy"]["requested"] != "L3", spec["autonomy"]


def test_explicit_end_to_end_still_reaches_l3():
    # Regression guard: when the user DOES attest end_to_end, L3 is still reachable.
    spec, report = d.build_spec(_answers(unattended=True, proven_manual_pass=True,
                                         proven_cheap=True, end_to_end=True))
    assert spec["autonomy"]["requested"] == "L3", spec["autonomy"]


# ---- Fix 1.5: the interview elicits every signal its own classifier branches on ----

def test_interview_elicits_step0_decision_keys():
    keys = {k for k, _ in d.QUESTIONS}
    for needed in ("deterministic_without_llm", "self_grading", "unattended", "agent_can_do_end_to_end"):
        assert needed in keys, f"interview never asks {needed!r}; that Step-0 branch can't fire interactively"


def test_agent_cannot_end_to_end_string_is_human_in_loop():
    # Interview answers arrive as strings; "no" must route to HUMAN_IN_LOOP, not slip through.
    report = d.classify_answers(_answers(agent_can_do_end_to_end="no"))
    assert report["verdict"] == "HUMAN_IN_LOOP", report


def test_agent_cannot_end_to_end_bool_false_is_human_in_loop():
    # Regression guard: an explicit JSON false must keep routing to HUMAN_IN_LOOP.
    report = d.classify_answers(_answers(agent_can_do_end_to_end=False))
    assert report["verdict"] == "HUMAN_IN_LOOP", report


def test_agent_end_to_end_unknown_does_not_force_human_in_loop():
    # Regression guard: a blank/unknown answer must NOT force human-in-the-loop.
    report = d.classify_answers(_answers(agent_can_do_end_to_end=""))
    assert report["verdict"] == "AUTONOMOUS_LOOP", report


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
