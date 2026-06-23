#!/usr/bin/env python3
"""Tests for the deterministic loop driver. Runs under pytest or standalone; no deps.

The driver is pure control flow with everything non-deterministic injected, so these
exercise it entirely with fakes -- no model, no network, no filesystem.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.runtime import run_loop, MemoryStore  # noqa: E402


def _spec(max_iterations=3, budget=None, no_progress=None, success=None):
    sc = {"max_iterations": max_iterations}
    if budget is not None:
        sc["budget"] = budget
    if no_progress is not None:
        sc["no_progress"] = no_progress
    if success is not None:
        sc["success"] = success
    return {"stop_conditions": sc}


def _counter():
    box = {"n": 0}

    def propose(_context):
        box["n"] += 1
        return f"change-{box['n']}"

    return box, propose


def test_driver_stops_at_max_iterations():
    box, propose = _counter()
    # distinct signals so no-progress never trips; no budget
    res = run_loop(_spec(max_iterations=3),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": c})
    assert res.reason == "max_iterations", res
    assert res.iterations == 3, res
    assert box["n"] == 3, box


def test_driver_stops_at_budget():
    # injected clock advances 5s per call; runtime cap is 10s
    ticks = {"v": -5.0}

    def clock():
        ticks["v"] += 5.0
        return ticks["v"]

    box, propose = _counter()
    res = run_loop(_spec(max_iterations=99, budget={"max_runtime_seconds": 10}),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": c},
                   clock=clock)
    assert res.reason == "budget", res
    assert box["n"] < 99, box


def test_driver_stops_on_no_progress_streak():
    box, propose = _counter()
    res = run_loop(_spec(max_iterations=99, no_progress={"signal": "stuck", "repeats": 2}),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": "stuck"})
    assert res.reason == "no_progress", res
    assert res.iterations == 2, res


def test_driver_keeps_on_pass_reverts_on_fail():
    kept, reverted = [], []
    results = iter([{"passed": False, "signal": "x"}, {"passed": True, "signal": "ok"}])
    _, propose = _counter()
    res = run_loop(_spec(max_iterations=5, success="gate passes"),
                   propose=propose,
                   verify=lambda c: next(results),
                   keep=lambda c, r: kept.append(c),
                   revert=lambda c, r: reverted.append(c))
    assert res.reason == "success" and res.success, res
    assert res.kept == 1 and len(kept) == 1, (res, kept)
    assert len(reverted) == 1, reverted


def test_driver_checkpoints_state_each_iteration():
    store = MemoryStore()
    _, propose = _counter()
    res = run_loop(_spec(max_iterations=3),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": c},
                   store=store)
    assert len(store.checkpoints) == res.iterations == 3, (store.checkpoints, res)


def test_driver_decides_stop_without_calling_the_model():
    # The stop decision is taken in code: propose is called exactly once per run iteration,
    # never for the terminal stop check.
    box, propose = _counter()
    res = run_loop(_spec(max_iterations=2),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": c})
    assert box["n"] == res.iterations == 2, (box, res)


def test_absent_evidence_is_failure_not_kept():
    # Fail-closed: a verify result with no explicit passed=True must revert, never keep.
    kept, reverted = [], []
    _, propose = _counter()
    res = run_loop(_spec(max_iterations=1),
                   propose=propose,
                   verify=lambda c: {},          # ambiguous / absent evidence
                   keep=lambda c, r: kept.append(c),
                   revert=lambda c, r: reverted.append(c))
    assert res.kept == 0 and not res.success, res
    assert kept == [] and len(reverted) == 1, (kept, reverted)


def test_ratchet_keeps_passed_then_reverts_only_later_failure():
    # A kept pass must survive a later failure: iter 1 passes -> keep change-1;
    # iter 2 fails -> revert change-2 (the LATEST), leaving prior kept work intact.
    # If revert wrongly rolled back everything, this would fail.
    kept, reverted = [], []
    results = iter([{"passed": True, "signal": "ok"}, {"passed": False, "signal": "bad"}])
    _, propose = _counter()
    res = run_loop(_spec(max_iterations=2),
                   propose=propose,
                   verify=lambda c: next(results),
                   keep=lambda c, r: kept.append(c),
                   revert=lambda c, r: reverted.append(c))
    assert res.kept == 1, res
    assert kept == ["change-1"], kept
    assert reverted == ["change-2"], reverted


def test_budget_check_happens_before_propose():
    # The runtime cap is checked at the TOP of the loop, before propose, so when
    # the budget is already spent the model is never called for that iteration.
    ticks = {"v": -5.0}

    def clock():
        ticks["v"] += 5.0
        return ticks["v"]

    box, propose = _counter()
    res = run_loop(_spec(max_iterations=99, budget={"max_runtime_seconds": 10}),
                   propose=propose,
                   verify=lambda c: {"passed": False, "signal": c},
                   clock=clock)
    assert res.reason == "budget", res
    assert res.iterations == 1, res          # cap tripped before the 2nd propose
    assert box["n"] == 1, box                # propose called exactly once


def test_only_explicit_passed_true_keeps():
    # Fail-closed contract: ONLY an explicit passed=True keeps. Truthy lookalikes
    # (the string "true", 1, an {ok:True} dict, or absent) must revert.
    _, propose = _counter()
    for verdict, should_keep in (
        ({"passed": True}, True),
        ({"passed": "true"}, False),
        ({"passed": 1}, False),
        ({"ok": True}, False),
        ({}, False),
    ):
        kept, reverted = [], []
        run_loop(_spec(max_iterations=1),
                 propose=propose,
                 verify=lambda c, v=verdict: v,
                 keep=lambda c, r: kept.append(c),
                 revert=lambda c, r: reverted.append(c))
        assert bool(kept) == should_keep, (verdict, kept, reverted)
        assert bool(reverted) == (not should_keep), (verdict, reverted)


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
