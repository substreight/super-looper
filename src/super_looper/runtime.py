#!/usr/bin/env python3
"""runtime.py - the deterministic loop driver. Super Looper's unique core primitive.

It runs a validated loop spec's *skeleton* in CODE: counts iterations, enforces the
budget and no-progress caps, applies the keep/revert ratchet, decides the stop, and
checkpoints state. Everything non-deterministic is INJECTED and never lives here:

  - propose(context) -> change        : the model's single creative step (the ONLY model call)
  - verify(change)  -> result         : the gate -- a tool, OUTSIDE the model
  - keep / revert(change, result)     : optional workspace effects (commit / undo)
  - store (.load()/.checkpoint())     : durable state on disk
  - clock () -> float                 : monotonic time, injected for testability

This module performs NO LLM call, network, or subprocess of its own. That is the point:
the loop is pulled out of the prompt, because counting, budgeting, and state are things
an LLM does expensively and unreliably, and code does cheaply and exactly.

  from super_looper.runtime import run_loop
  result = run_loop(spec, propose=propose, verify=verify, store=FileStore("state.json"))
"""
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RunResult:
    reason: str                 # success | max_iterations | budget | no_progress
    success: bool
    iterations: int
    kept: int
    history: List[Dict[str, Any]]
    state: Dict[str, Any]


class MemoryStore:
    """In-memory durable state. Default store; also the test double."""

    def __init__(self, state: Optional[Dict[str, Any]] = None):
        self._state = dict(state or {})
        self.checkpoints: List[Dict[str, Any]] = []

    def load(self) -> Dict[str, Any]:
        return dict(self._state)

    def checkpoint(self, state: Dict[str, Any]) -> None:
        self._state = dict(state)
        self.checkpoints.append(dict(state))


class FileStore:
    """Durable state as a JSON file on disk -- state out of the context window."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (ValueError, OSError):
            return {}

    def checkpoint(self, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")


def _noop(*_args, **_kwargs) -> None:
    return None


def _as_result(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {"passed": bool(value)}


def _budget_exceeded(budget: Dict[str, Any], spent: Dict[str, float], elapsed: float) -> bool:
    if not budget:
        return False
    mr = budget.get("max_runtime_seconds")
    if isinstance(mr, (int, float)) and not isinstance(mr, bool) and elapsed >= mr:
        return True
    mt = budget.get("max_tokens")
    if isinstance(mt, (int, float)) and not isinstance(mt, bool) and spent["tokens"] >= mt:
        return True
    mc = budget.get("max_cost_usd")
    if isinstance(mc, (int, float)) and not isinstance(mc, bool) and spent["cost"] >= mc:
        return True
    return False


def run_loop(
    spec: Dict[str, Any],
    *,
    propose: Callable[[Dict[str, Any]], Any],
    verify: Callable[[Any], Any],
    keep: Optional[Callable[[Any, Dict[str, Any]], None]] = None,
    revert: Optional[Callable[[Any, Dict[str, Any]], None]] = None,
    store: Any = None,
    clock: Optional[Callable[[], float]] = None,
) -> RunResult:
    """Run the loop's deterministic skeleton. See module docstring for the contract."""
    spec = spec if isinstance(spec, dict) else {}
    sc = spec.get("stop_conditions") if isinstance(spec.get("stop_conditions"), dict) else {}

    max_iter = sc.get("max_iterations")
    if not isinstance(max_iter, int) or isinstance(max_iter, bool) or max_iter < 1:
        max_iter = 1
    budget = sc.get("budget") if isinstance(sc.get("budget"), dict) else {}
    no_progress = sc.get("no_progress") if isinstance(sc.get("no_progress"), dict) else {}
    repeats = no_progress.get("repeats")
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        repeats = None
    has_success_exit = bool(sc.get("success"))

    store = store if store is not None else MemoryStore()
    clock = clock or time.monotonic
    keep = keep or _noop
    revert = revert or _noop

    state = store.load() if hasattr(store, "load") else {}
    if not isinstance(state, dict):
        state = {}

    start = clock()
    spent = {"tokens": 0.0, "cost": 0.0}
    streak = 0
    last_signal: Optional[str] = None
    history: List[Dict[str, Any]] = []
    kept = 0
    iterations = 0
    reason: Optional[str] = None
    success = False

    while True:
        # Deterministic stop checks -- decided in code, BEFORE any model call.
        if iterations >= max_iter:
            reason = "max_iterations"
            break
        if _budget_exceeded(budget, spent, clock() - start):
            reason = "budget"
            break
        if repeats is not None and streak >= repeats:
            reason = "no_progress"
            break

        iterations += 1
        context = {"iteration": iterations, "last_signal": last_signal, "state": dict(state)}
        change = propose(context)                      # the one creative step
        result = _as_result(verify(change))            # the gate, outside the model

        spent["tokens"] += float(result.get("tokens") or 0)
        spent["cost"] += float(result.get("cost") or 0.0)

        # Fail-closed ratchet: only an explicit passed=True keeps; anything else reverts.
        if result.get("passed") is True:
            keep(change, result)
            kept += 1
            streak = 0
            last_signal = None
            state["last_kept_iteration"] = iterations
            history.append({"iteration": iterations, "kept": True, "signal": result.get("signal")})
            store.checkpoint(state)
            if has_success_exit:
                reason = "success"
                success = True
                break
        else:
            revert(change, result)
            signal = result.get("signal")
            streak = streak + 1 if (signal is not None and signal == last_signal) else 1
            last_signal = signal
            history.append({"iteration": iterations, "kept": False, "signal": signal})
            store.checkpoint(state)

    return RunResult(
        reason=reason or "max_iterations",
        success=success,
        iterations=iterations,
        kept=kept,
        history=history,
        state=state,
    )
