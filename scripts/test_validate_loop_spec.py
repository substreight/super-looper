#!/usr/bin/env python3
"""Tests for validate_loop_spec.

Runs under pytest, or standalone with no test runner:  python test_validate_loop_spec.py
Zero third-party deps required (mirrors the validator's own zero-dep promise).
"""
import copy
import json
import os
import random
import tempfile

import validate_loop_spec as v

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "examples", "nightly-export.loop.json")
with open(EXAMPLE) as _f:
    GOOD = json.load(_f)


def _spec(**overrides):
    s = copy.deepcopy(GOOD)
    s.update(overrides)
    return s


def _drop(d, key):
    d = copy.deepcopy(d)
    d.pop(key, None)
    return d


# ---- the worked example must stay perfectly clean ----

def test_good_example_is_clean():
    errors, warnings = v.validate(GOOD)
    assert errors == [], errors
    assert warnings == [], warnings


# ---- existing non-negotiables still fire ----

def test_self_rung_errors():
    s = _spec(verifier={"rung": "self", "check": "the model thinks it is right"})
    errors, _ = v.validate(s)
    assert any("off the ladder" in e for e in errors), errors


def test_on_disk_false_errors():
    s = _spec(state={"architecture": "fresh_restart", "on_disk": False})
    errors, _ = v.validate(s)
    assert any("on_disk" in e for e in errors), errors


def test_parallel_without_isolation_errors():
    s = _spec(execution={"parallelism": 3, "isolation": "none"})
    errors, _ = v.validate(s)
    assert any("parallelism" in e for e in errors), errors


# ---- Bug 3: budget is an error when unattended, a warning otherwise ----

def test_unattended_without_budget_errors():
    s = _spec(stop_conditions=_drop(GOOD["stop_conditions"], "budget"))  # example is unattended
    errors, _ = v.validate(s)
    assert any("budget" in e for e in errors), errors


def test_attended_without_budget_warns_only():
    s = _spec(stop_conditions=_drop(GOOD["stop_conditions"], "budget"),
              trigger={"type": "manual", "unattended": False})
    s.pop("autonomy", None)
    errors, warnings = v.validate(s)
    assert not any("budget" in e for e in errors), errors
    assert any("budget" in w for w in warnings), warnings


# ---- Bug 4: success required for completion, optional for cadence ----

def test_completion_requires_success_structurally():
    s = _spec(loop_shape="completion",
              stop_conditions=_drop(GOOD["stop_conditions"], "success"))
    errors, _ = v.validate(s)
    assert any("success" in e for e in errors), errors


def test_cadence_allows_missing_success():
    s = _spec(loop_shape="cadence",
              stop_conditions={"max_iterations": 5,
                               "budget": {"max_runtime_seconds": 600},
                               "no_progress": {"signal": "no new PRs", "repeats": 3}},
              trigger={"type": "schedule", "detail": "every 15m", "unattended": True})
    errors, _ = v.validate(s)
    assert not any("success" in e.lower() for e in errors), errors


def test_builtin_path_requires_completion_success():
    # exercise the dependency-free checker directly (independent of jsonschema)
    s = _spec(loop_shape="completion",
              stop_conditions=_drop(GOOD["stop_conditions"], "success"))
    errs = v._builtin_structural(s)
    assert any("success" in e for e in errs), errs


# ---- Tier 1: gate-quality floor ----

def test_weasel_gate_warns():
    s = _spec(verifier={"rung": "tool", "check": "the output looks good"})
    _, warnings = v.validate(s)
    assert any("taste judgment" in w for w in warnings), warnings


def test_non_measurable_gate_warns():
    s = _spec(verifier={"rung": "tool", "check": "the report is acceptable"})
    _, warnings = v.validate(s)
    assert any("machine-decidable" in w for w in warnings), warnings


def test_incoherent_evidence_warns():
    g = copy.deepcopy(GOOD["goal"])
    g["evidence"] = "completely unrelated banana"
    s = _spec(goal=g)
    _, warnings = v.validate(s)
    assert any("evidence shares no term" in w for w in warnings), warnings


def test_incoherent_success_warns():
    sc = copy.deepcopy(GOOD["stop_conditions"])
    sc["success"] = "the moon is full tonight"
    s = _spec(stop_conditions=sc)
    _, warnings = v.validate(s)
    assert any("success shares no term" in w for w in warnings), warnings


# ---- render round-trips ----

def test_render_runs():
    out = v.render(GOOD)
    assert "GOAL:" in out and "VERIFY:" in out


# ---- regression corpus: known-bad specs must keep tripping their lints ----
# Each row: (name, spec, error-substrings that must appear, warning-substrings that must appear).

BAD_CORPUS = [
    ("self_rung",
     _spec(verifier={"rung": "self", "check": "the model thinks it is right"}),
     ["off the ladder"], []),
    ("on_disk_false",
     _spec(state={"architecture": "compaction", "on_disk": False}),
     ["on_disk"], []),
    ("independent_contradiction",
     _spec(verifier={"rung": "independent_model", "check": "reviewer approves the diff",
                     "independent": False}),
     ["independent"], []),
    ("parallel_no_isolation",
     _spec(execution={"parallelism": 2, "isolation": "none"}),
     ["parallelism"], []),
    ("unattended_no_budget",
     _spec(stop_conditions=_drop(GOOD["stop_conditions"], "budget")),
     ["budget"], []),
    ("missing_no_progress",
     _spec(stop_conditions=_drop(GOOD["stop_conditions"], "no_progress")),
     ["no_progress"], []),
    ("metered_unattended",
     _spec(economics={"billing": "metered"}),
     [], ["metered"]),
    ("weasel_gate",
     _spec(verifier={"rung": "tool", "check": "output looks good", "end_to_end": True}),
     [], ["taste judgment"]),
    ("human_gate",
     _spec(verifier={"rung": "human", "check": "a person signs off on the result"}),
     [], ["human-in-the-loop"]),
    ("cadence_with_success",
     _spec(loop_shape="cadence"),
     [], ["cadence"]),
]


def test_bad_corpus():
    for name, spec, exp_err, exp_warn in BAD_CORPUS:
        errors, warnings = v.validate(spec)
        blob_e, blob_w = " || ".join(errors), " || ".join(warnings)
        for sub in exp_err:
            assert sub in blob_e, f"[{name}] expected error containing {sub!r}; got {errors}"
        for sub in exp_warn:
            assert sub in blob_w, f"[{name}] expected warning containing {sub!r}; got {warnings}"


# ---- robustness: validate() is a harness gate, so it must never raise ----

def test_fuzz_validate_never_raises():
    random.seed(1234)
    junk = [None, 0, 1, -1, "", "x", [], {}, [1, 2], {"k": "v"}, True, False, 3.14, "looks good"]
    keys = list(GOOD.keys()) + ["report", "maker", "checker", "execution", "economics", "meta"]
    for _ in range(400):
        spec = copy.deepcopy(GOOD)
        for _ in range(random.randint(1, 6)):
            roll, k = random.random(), random.choice(keys)
            if roll < 0.4:
                spec.pop(k, None)
            elif roll < 0.8:
                spec[k] = random.choice(junk)
            else:
                spec["junk_" + k] = random.choice(junk)
        errors, warnings = v.validate(spec)
        assert isinstance(errors, list) and isinstance(warnings, list)
    for bad in (None, 5, "x", [1], 3.2, True):
        errors, warnings = v.validate(bad)
        assert isinstance(errors, list) and isinstance(warnings, list)


def test_semantic_tolerates_malformed_subobjects():
    # _semantic assumes structural already passed; harden it anyway so the gate can't crash.
    weird = copy.deepcopy(GOOD)
    weird.update(maker="not a dict", verifier=["also", "wrong"], economics=5, trigger="nightly")
    errors, warnings = v._semantic(weird)
    assert isinstance(errors, list) and isinstance(warnings, list)


def test_cli_render_on_malformed_does_not_crash():
    weird = _spec(verifier="broken")
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(weird, f)
    try:
        rc = v._main(["prog", path, "--render"])  # must surface errors, not a traceback
        assert isinstance(rc, int)
    finally:
        os.unlink(path)


def test_single_pass_loop_warns():
    sc = copy.deepcopy(GOOD["stop_conditions"])
    sc["max_iterations"] = 1
    s = _spec(stop_conditions=sc)
    _, warnings = v.validate(s)
    assert any("max_iterations is 1" in w for w in warnings), warnings


def test_multi_pass_loop_does_not_warn_single_pass():
    # the worked example (max_iterations 3) must not trip the single-pass warning
    _, warnings = v.validate(GOOD)
    assert not any("max_iterations is 1" in w for w in warnings), warnings


# ---- autonomy dial ----

def test_good_example_earns_l3():
    # nightly-export has a rung-1 end-to-end gate, trigger, budget, scope fence,
    # reversible output, and a proven manual pass -> top level.
    level, missing = v.max_autonomy(GOOD)
    assert level == "L3", (level, missing)
    assert missing == [], missing


def test_self_rung_caps_at_l1():
    level, missing = v.max_autonomy(_spec(verifier={"rung": "self", "check": "x"}))
    assert level == "L1", (level, missing)


def test_independent_model_caps_at_l2():
    s = _spec(verifier={"rung": "independent_model", "check": "reviewer ok", "independent": True})
    level, _ = v.max_autonomy(s)
    assert level == "L2", level


def test_request_within_ceiling_ok():
    s = _spec()  # GOOD requests and earns L3
    errors, _ = v.validate(s)
    assert not any("autonomy.requested" in e for e in errors), errors


def test_request_l3_without_gate_errors():
    s = _spec(verifier={"rung": "self", "check": "x"}, autonomy={"requested": "L3"})
    errors, _ = v.validate(s)
    assert any("only earned L1" in e for e in errors), errors


def test_request_l3_without_budget_errors():
    s = _spec(stop_conditions=_drop(GOOD["stop_conditions"], "budget"))
    errors, _ = v.validate(s)
    assert any("only earned L1" in e and "budget cap" in e for e in errors), errors


def test_request_l2_without_budget_errors():
    s = _spec(stop_conditions=_drop(GOOD["stop_conditions"], "budget"),
              autonomy={"requested": "L2"})
    errors, _ = v.validate(s)
    assert any("only earned L1" in e and "budget cap" in e for e in errors), errors


def test_request_l2_without_scope_fence_errors():
    scope = copy.deepcopy(GOOD["scope"])
    scope.pop("must_not_touch", None)
    s = _spec(scope=scope, autonomy={"requested": "L2"})
    errors, _ = v.validate(s)
    assert any("only earned L1" in e and "blast-radius fence" in e for e in errors), errors


def test_request_l3_without_trigger_errors():
    s = _spec()
    s.pop("trigger", None)
    errors, _ = v.validate(s)
    assert any("only earned L2" in e and "unattended trigger" in e for e in errors), errors


def test_request_l3_without_reversibility_errors():
    s = _spec(autonomy={"requested": "L3", "proven_manual_pass": True})
    errors, _ = v.validate(s)
    assert any("only earned L2" in e and "output_reversibility" in e for e in errors), errors


def test_request_l3_without_manual_pass_errors_even_if_cheap():
    s = _spec(autonomy={"requested": "L3", "output_reversibility": "reversible"},
              economics={"billing": "prepaid", "proven_cheap": True})
    errors, _ = v.validate(s)
    assert any("only earned L2" in e and "proven_manual_pass" in e for e in errors), errors


def test_request_l3_without_end_to_end_errors():
    verifier = copy.deepcopy(GOOD["verifier"])
    verifier.pop("end_to_end", None)
    s = _spec(verifier=verifier)
    errors, _ = v.validate(s)
    assert any("only earned L2" in e and "end-to-end" in e for e in errors), errors


def test_irreversible_output_caps_below_l3():
    s = _spec(autonomy={"requested": "L3", "output_reversibility": "irreversible"})
    errors, _ = v.validate(s)
    assert any("only earned L2" in e and "irreversible" in e for e in errors), errors


def test_dialing_down_always_ok():
    s = _spec(verifier={"rung": "self", "check": "x"}, autonomy={"requested": "L1"})
    errors, _ = v.validate(s)
    assert not any("autonomy.requested" in e for e in errors), errors  # no autonomy error; self-rung error is separate


def test_render_plain_mentions_autonomy():
    out = v.render_plain(GOOD)
    assert isinstance(out, str) and "max safe autonomy" in out and "L3" in out


def test_autonomy_schema_field_is_optional_and_valid():
    # adding the autonomy block must not break structural validation
    errors, warnings = v.validate(_spec(autonomy={"requested": "L2", "output_reversibility": "reversible"}))
    assert errors == [], errors


def test_builtin_structural_rejects_bad_parallelism_type():
    s = _spec(execution={"parallelism": "2", "isolation": "none"})
    errors = v._builtin_structural(s)
    assert any("execution.parallelism" in e and "integer" in e for e in errors), errors


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
