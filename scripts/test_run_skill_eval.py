#!/usr/bin/env python3
"""Tests for the blind skill-eval runner. Runs under pytest or standalone; needs NO API key.

These cover the deterministic logic (prompt construction, response parsing, blindness).
The live Anthropic call in main() is thin glue and is exercised only by the secret-gated CI job.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVALS = os.path.join(ROOT, "evals")
if EVALS not in sys.path:
    sys.path.insert(0, EVALS)

import run_skill_eval as r  # noqa: E402


def test_build_messages_puts_skill_in_system_and_task_in_user():
    system, user = r.build_messages("SKILL BODY HERE", "Should I loop my nightly export?")
    assert "SKILL BODY HERE" in system
    assert "nightly export" in user


def test_build_messages_is_blind_to_the_answer_key():
    _, user = r.build_messages("SKILL", "some task")
    for leak in ("expected_verdict", "acceptable_verdicts", "must_mention"):
        assert leak not in user, leak


def test_parse_response_extracts_and_uppercases_verdict():
    out = r.parse_response('{"verdict": "use_scheduler", "rationale": "a script suffices"}')
    assert out["verdict"] == "USE_SCHEDULER"
    assert "script" in out["rationale"]


def test_parse_response_tolerates_prose_and_code_fences():
    text = 'Sure.\n```json\n{"verdict":"NOT_A_LOOP","rationale":"one-shot"}\n```\nThanks!'
    out = r.parse_response(text)
    assert out["verdict"] == "NOT_A_LOOP", out


def test_parse_response_unparseable_yields_empty_verdict():
    out = r.parse_response("I really cannot decide here.")
    assert out["verdict"] == "", out


def test_run_eval_sends_only_the_blind_built_message():
    # The injected model must receive EXACTLY build_messages(skill, prompt) -- nothing
    # derived from the scenario's expected_verdict / acceptable_verdicts / must_mention.
    scenarios = [{"id": "s1", "prompt": "P1", "expected_verdict": "USE_SCHEDULER",
                  "acceptable_verdicts": ["NOT_A_LOOP"], "must_mention": ["scheduler"]}]
    captured = {}

    def fake_ask(system, user):
        captured["system"], captured["user"] = system, user
        return '{"verdict":"NOT_A_LOOP","rationale":"r"}'

    results = r.run_eval("SK", scenarios, fake_ask)
    exp_system, exp_user = r.build_messages("SK", "P1")
    assert captured["system"] == exp_system
    assert captured["user"] == exp_user
    assert results == [{"id": "s1", "verdict": "NOT_A_LOOP", "rationale": "r"}]


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
