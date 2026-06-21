#!/usr/bin/env python3
"""
validate_loop_spec.py - validate a loop spec against the loop-design discipline,
and render the human-readable spec from it.

Two layers of checking:
  1. Structural - required fields, types, enums (mirrors loop-spec.schema.json).
     Uses the `jsonschema` library if installed; otherwise a built-in checker
     covering the same non-negotiables, so this runs anywhere with no deps.
  2. Semantic lint - the skill's judgment calls that JSON Schema can't express
     (self-grading is off the ladder, parallel needs isolation, metered +
     unattended is risky, same-model checker is the weakest gate, etc.).

Usage:
    python validate_loop_spec.py spec.json            # validate; exit 1 on error
    python validate_loop_spec.py spec.json --render    # print human-readable spec
    python validate_loop_spec.py spec.json --explain   # print a plain-language preview
    python validate_loop_spec.py spec.json --strict    # treat warnings as errors

Importable:
    from validate_loop_spec import validate, render, render_plain, max_autonomy
    errors, warnings = validate(spec_dict)
    level, missing = max_autonomy(spec_dict)   # highest autonomy the loop has earned
"""

import json
import os
import re
import sys


def _find_schema():
    """Locate the schema across the layouts this skill ships in (flat, or scripts/+schemas/)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "loop-spec.schema.json"),
        os.path.join(here, "..", "schemas", "loop-spec.schema.json"),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


# Gate-quality heuristics. These RAISE THE FLOOR; they do not judge whether a gate is good.
# A gate's real quality is a property of how it behaves on real inputs, not of the spec text.
_WEASEL = (
    "looks good", "look good", "looks right", "looks fine", "looks reasonable",
    "is correct", "seems correct", "seems right", "seems fine", "good enough",
    "high quality", "high-quality", "is good", "feels good", "makes sense",
    "reads well", "is better", "much better", "is nicer",
)

_MEASURABLE = re.compile(
    r"[<>=]=?|!=|\b\d+\b|\b(exit|exits|exited|pass|passes|passed|passing|fail|fails|failed|failing|"
    r"green|red|valid|invalid|schema|zero|empty|count|status|code|returns?|equals?|matches?|match|"
    r"true|false|success|error|errors|warnings?|compiles?|builds?|lint|tests?|threshold|exists?)\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "must", "not", "all", "any", "are", "was",
    "its", "but", "has", "have", "from", "into", "out", "per", "via", "than", "then",
    "when", "where", "what", "which", "should", "would", "could", "does", "did",
}


def _weasel(text):
    low = (text or "").lower()
    for phrase in _WEASEL:
        if phrase in low:
            return phrase
    return None


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9_]+", (text or "").lower())
            if len(t) >= 3 and t not in _STOPWORDS}


def _d(x):
    """Coerce to dict so the semantic lint never raises on a malformed sub-object."""
    return x if isinstance(x, dict) else {}


_AUTONOMY_ORDER = ["L0", "L1", "L2", "L3"]


def max_autonomy(spec):
    """Compute the highest autonomy level a loop has EARNED, plus what's missing to go higher.

    Returns (level, missing): level in L0..L3, missing = the gaps blocking the next level.
    Autonomy is earned, never chosen: the ceiling is set by the gate rung, then capped by
    the budget cap, scope fence, output reversibility, and a proven manual pass. Pure; reads
    the same fields the semantic checks read.
    """
    spec = _d(spec)
    verifier = _d(spec.get("verifier"))
    scope = _d(spec.get("scope"))
    sc = _d(spec.get("stop_conditions"))
    economics = _d(spec.get("economics"))
    reversibility = _d(spec.get("autonomy")).get("output_reversibility")
    rung = verifier.get("rung")

    # The gate rung sets the hard ceiling.
    if rung in ("self", None):
        return "L1", ["a real gate (verifier.rung 'tool' or 'independent_model' — self/none can't run unsupervised)"]
    if rung == "human":
        return "L1", ["an automatic gate (a human gate is human-in-the-loop by definition)"]

    # rung is 'tool' or 'independent_model': L2 is reachable; L3 needs every guardrail.
    missing = []
    if rung != "tool":
        missing.append("a rung-1 tool gate on the deliverable (independent_model tops out at L2)")
    if not sc.get("budget"):
        missing.append("a budget cap (stop_conditions.budget)")
    if not scope.get("must_not_touch"):
        missing.append("a blast-radius fence (scope.must_not_touch)")
    if reversibility not in (None, "reversible"):
        missing.append(f"reversible output (it's {reversibility} — a human must own the irreversible step)")
    if not economics.get("proven_cheap"):
        missing.append("a proven manual pass (economics.proven_cheap)")
    return ("L3", []) if not missing else ("L2", missing)


ENUMS = {
    ("loop_shape",): ["completion", "cadence"],
    ("verifier", "rung"): ["tool", "independent_model", "human", "self"],
    ("state", "architecture"): ["fresh_restart", "compaction"],
    ("trigger", "type"): ["schedule", "event", "manual"],
    ("execution", "isolation"): ["none", "worktree", "sandbox"],
    ("economics", "billing"): ["prepaid", "metered", "unknown"],
}


# ---------- structural validation ----------

def _builtin_structural(spec):
    """Minimal structural check used when jsonschema isn't installed."""
    errors = []
    required_top = ["name", "goal", "scope", "loop_shape", "verifier", "state",
                    "stop_conditions", "on_stop"]
    for k in required_top:
        if k not in spec:
            errors.append(f"missing required field: {k}")

    def req(obj, path, keys):
        for k in keys:
            if not isinstance(obj, dict) or k not in obj or obj.get(k) in (None, "", [], {}):
                errors.append(f"missing/empty required field: {path}.{k}")

    if isinstance(spec.get("goal"), dict):
        req(spec["goal"], "goal", ["end_state", "evidence", "budget"])
        if "constraints" not in spec["goal"]:
            errors.append("missing required field: goal.constraints (use [] if none, deliberately)")
    if isinstance(spec.get("scope"), dict):
        if not spec["scope"].get("may_touch"):
            errors.append("missing/empty required field: scope.may_touch")
    if isinstance(spec.get("verifier"), dict):
        req(spec["verifier"], "verifier", ["rung", "check"])
    if isinstance(spec.get("state"), dict):
        if "on_disk" not in spec["state"]:
            errors.append("missing required field: state.on_disk")
        if "architecture" not in spec["state"]:
            errors.append("missing required field: state.architecture")
    sc = spec.get("stop_conditions")
    if isinstance(sc, dict):
        # success is the finish line of a completion loop; cadence loops run open-ended.
        required_sc = ["success", "max_iterations"] if spec.get("loop_shape") == "completion" \
            else ["max_iterations"]
        req(sc, "stop_conditions", required_sc)
        if not isinstance(sc.get("no_progress"), dict):
            errors.append("missing required field: stop_conditions.no_progress")
        else:
            req(sc["no_progress"], "stop_conditions.no_progress", ["signal", "repeats"])

    # enum checks
    for path, allowed in ENUMS.items():
        obj = spec
        ok = True
        for p in path[:-1]:
            obj = obj.get(p) if isinstance(obj, dict) else None
            if obj is None:
                ok = False
                break
        if ok and isinstance(obj, dict) and path[-1] in obj:
            val = obj[path[-1]]
            if val not in allowed:
                errors.append(f"{'.'.join(path)} must be one of {allowed}, got {val!r}")
    return errors


def _structural(spec):
    schema_path = _find_schema()
    if schema_path is not None:
        try:
            import jsonschema  # type: ignore
            with open(schema_path) as f:
                schema = json.load(f)
            v = jsonschema.Draft202012Validator(schema)
            return [f"{'.'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
                    for e in sorted(v.iter_errors(spec), key=lambda e: list(e.path))]
        except (ImportError, OSError, ValueError):
            pass  # missing lib OR missing/garbled schema file -> built-in checker below
    return _builtin_structural(spec)


# ---------- semantic lint (the skill's judgment) ----------

def _semantic(spec):
    errors, warnings = [], []
    verifier = _d(spec.get("verifier"))
    state = _d(spec.get("state"))
    trigger = _d(spec.get("trigger"))
    execution = _d(spec.get("execution"))
    economics = _d(spec.get("economics"))
    maker = _d(spec.get("maker"))
    checker = _d(spec.get("checker"))
    sc = _d(spec.get("stop_conditions"))
    unattended = bool(trigger.get("unattended"))

    rung = verifier.get("rung")
    # The maker grading itself is off the ladder.
    if rung == "self":
        errors.append(
            "verifier.rung is 'self': the maker grading its own work is off the ladder. "
            "Self-correction without external feedback often leaves output the same or worse. "
            "Use a tool gate, an independent model, or a human gate.")
    if rung == "independent_model" and verifier.get("independent") is False:
        errors.append("verifier.rung is 'independent_model' but independent=false. Contradiction: "
                      "the checker must be separate from the maker and not given its justification.")
    if rung == "human":
        warnings.append("verifier.rung is 'human': this loop is human-in-the-loop, not autonomous. "
                        "Make sure that's named honestly and the cadence respects review throughput.")

    # Unattended loops need a real, ideally end-to-end gate.
    if unattended and rung in ("self", None):
        errors.append("trigger.unattended is true but there is no trustworthy gate. An unattended loop "
                      "without an independent/tool verifier ships confidently-wrong work while you sleep.")
    if unattended and rung == "tool" and verifier.get("end_to_end") is not True:
        warnings.append("Unattended tool-gated loop without end_to_end verification. The strongest gate "
                        "exercises the real system (live endpoint, browser, simulator); self-reported unit "
                        "results alone are the classic overnight failure.")

    # State must live outside the context window.
    if state.get("on_disk") is False:
        errors.append("state.on_disk is false: durable state in the conversation is the context-accumulation "
                      "anti-pattern (cost compounds, recall rots). Externalize to files/board.")
    if state.get("architecture") == "fresh_restart" and not state.get("durable_progress"):
        warnings.append("fresh_restart architecture but no durable_progress files listed. A fresh context "
                        "each pass with nothing to reload will repeat work or lose the plan.")

    # Same-model checker is the weakest form of rung 2.
    if rung == "independent_model" and maker.get("model") and maker.get("model") == checker.get("model"):
        warnings.append("maker.model == checker.model: a same-model checker favors its own generations. "
                        "Prefer a different model/family for the gate.")

    # Concurrency without isolation -> parallel clobber.
    if execution.get("parallelism", 1) and execution.get("parallelism", 1) > 1:
        if execution.get("isolation", "none") == "none":
            errors.append("execution.parallelism > 1 with isolation 'none': concurrent agents will overwrite "
                          "each other. Use a git worktree or sandbox per agent.")

    # Economics gate.
    if unattended and economics.get("billing") == "metered" and not economics.get("proven_cheap"):
        warnings.append("Unattended loop on metered billing that isn't proven cheap per accepted change. "
                        "Overnight loops have produced five-figure daily bills. Prove cost first or move to "
                        "prepaid/flat-rate capacity.")

    # Budget cap: a warning when attended, but an unattended loop with no cost ceiling is the
    # five-figure-overnight-bill failure mode, so it's an error there.
    if not sc.get("budget"):
        if unattended:
            errors.append("trigger.unattended is true but stop_conditions.budget is absent. An unattended loop "
                          "with no token/cost/runtime cap is the overnight-runaway-bill failure mode. Set a cap.")
        else:
            warnings.append("stop_conditions.budget is absent. A token/cost/runtime cap protects the bill as much "
                            "as the iteration cap does, especially unattended.")

    # Cadence loops run open-ended; a 'success' exit is fine as per-run success but may signal a mislabel.
    if spec.get("loop_shape") == "cadence" and sc.get("success"):
        warnings.append("loop_shape is 'cadence' but a 'success' exit is set. That's fine if it means per-run "
                        "success; but if there's a single real finish line, this may be a 'completion' loop.")

    # A loop capped at one pass never iterates toward its gate -- it's a single shot, not a loop.
    if sc.get("max_iterations") == 1:
        warnings.append("stop_conditions.max_iterations is 1: this runs a single pass and never iterates toward "
                        "the gate, so it isn't really a loop. If that's intended, it's a scheduled one-shot "
                        "generation -- use cron/Task Scheduler and call it that; if it should retry on failure, "
                        "raise the cap. (A tool gate on delivery/plumbing here does not gate the actual output.)")

    # --- Gate-quality floor: the validator's blindest spot. Raise the floor; never claim to judge quality. ---
    goal = _d(spec.get("goal"))
    check = verifier.get("check") or ""
    end_state = goal.get("end_state") or ""

    # A gate phrased as a taste judgment with no measurable backing is the most expensive bug this skill names.
    weasel = _weasel(check) or _weasel(end_state)
    if weasel:
        warnings.append(f"verifier.check / goal.end_state reads as a taste judgment ({weasel!r}). A gate the maker "
                        "can argue its way past won't reliably fail bad work. State it so a tool or a different "
                        "model can decide it (exit code, threshold, schema, match).")

    # A gate with no operator, number, or pass/fail token may not be machine-decidable.
    if check and not _weasel(check) and not _MEASURABLE.search(check):
        warnings.append("verifier.check has no operator, count, or pass/fail token, so it may not be "
                        "machine-decidable. Prefer a check a tool can run and that can actually return 'fail'.")

    # Coherence: the parts of the spec should refer to the same thing.
    if _tokens(goal.get("evidence")) and _tokens(check) and not (_tokens(goal.get("evidence")) & _tokens(check)):
        warnings.append("goal.evidence shares no term with verifier.check. The evidence should describe what the "
                        "gate actually checks; if they're unrelated, one of them is wrong.")
    if _tokens(sc.get("success")) and _tokens(end_state) and not (_tokens(sc.get("success")) & _tokens(end_state)):
        warnings.append("stop_conditions.success shares no term with goal.end_state. The success exit and the "
                        "goal should name the same finish line.")

    # Autonomy dial: the requested level must not exceed what the loop has earned.
    requested = _d(spec.get("autonomy")).get("requested")
    if requested in _AUTONOMY_ORDER:
        earned, missing = max_autonomy(spec)
        if _AUTONOMY_ORDER.index(requested) > _AUTONOMY_ORDER.index(earned):
            errors.append(f"autonomy.requested is {requested} but this loop has only earned {earned}. To reach "
                          f"{requested}, add: " + "; ".join(missing) + ". Dial down freely; you can only dial up "
                          "when the gate licenses it.")

    return errors, warnings


def validate(spec):
    """Return (errors, warnings). Never raises, so a harness can gate on it safely.
    Structural errors short-circuit the semantic lint."""
    if not isinstance(spec, dict):
        return [f"spec must be a JSON object, got {type(spec).__name__}"], []
    structural = _structural(spec)
    if structural:
        return structural, []
    return _semantic(spec)


# ---------- human-readable renderer ----------

def render(spec):
    g = spec.get("goal", {})
    sc = spec.get("stop_conditions", {})
    v = spec.get("verifier", {})
    st = spec.get("state", {})
    lines = []
    lines.append(f"GOAL:        {g.get('end_state', '')}")
    if g.get("evidence"):
        lines.append(f"  evidence:  {g['evidence']}")
    if g.get("constraints"):
        lines.append(f"  constraints: {', '.join(g['constraints'])}")
    if g.get("budget"):
        lines.append(f"  budget:    {g['budget']}")
    scope = spec.get("scope", {})
    may = ", ".join(scope.get("may_touch", []))
    nott = ", ".join(scope.get("must_not_touch", []))
    lines.append(f"SCOPE:       may touch {may}" + (f"; never {nott}" if nott else ""))
    if spec.get("trigger"):
        t = spec["trigger"]
        lines.append(f"TRIGGER:     {t.get('type')}" + (f" - {t['detail']}" if t.get("detail") else "")
                     + ("  [unattended]" if t.get("unattended") else ""))
    lines.append(f"SHAPE:       {spec.get('loop_shape', '')}")
    if spec.get("iteration"):
        lines.append("EACH ITERATION (clean context):")
        for i, step in enumerate(spec["iteration"], 1):
            lines.append(f"  {i}. {step}")
    rung_label = {"tool": "rung 1 - tool/computational", "independent_model": "rung 2 - independent model",
                  "human": "rung 3 - human", "self": "OFF LADDER - self-grading"}.get(v.get("rung"), v.get("rung"))
    e2e = " (end-to-end)" if v.get("end_to_end") else ""
    lines.append(f"VERIFY:      {v.get('check', '')}  [{rung_label}{e2e}]")
    progress = ", ".join(st.get("durable_progress", []))
    context = ", ".join(st.get("durable_context", []))
    lines.append(f"STATE:       {st.get('architecture', '')}, on disk"
                 + (f"; progress: {progress}" if progress else "")
                 + (f"; context: {context}" if context else ""))
    stop_bits = []
    if sc.get("success"):
        stop_bits.append(sc["success"])
    if sc.get("max_iterations"):
        stop_bits.append(f"{sc['max_iterations']} iterations")
    if sc.get("budget"):
        b = sc["budget"]
        stop_bits.append("budget(" + ", ".join(f"{k}={val}" for k, val in b.items()) + ")")
    if sc.get("no_progress"):
        np = sc["no_progress"]
        stop_bits.append(f"{np.get('signal')} x{np.get('repeats')}")
    lines.append("STOP WHEN:   " + "  OR  ".join(stop_bits))
    lines.append(f"ON STOP:     {spec.get('on_stop', '')}")
    if spec.get("report", {}).get("destination"):
        lines.append(f"REPORT:      {spec['report']['destination']}")
    maker, checker = spec.get("maker", {}), spec.get("checker", {})
    if maker or checker:
        m = f"{maker.get('model', '?')}/{maker.get('effort', '?')}" if maker else "-"
        c = f"{checker.get('model', '?')}/{checker.get('effort', '?')}" if checker else "-"
        lines.append(f"MAKER:       {m}   CHECKER: {c}")
    ex = spec.get("execution", {})
    if ex.get("parallelism", 1) > 1 or ex.get("isolation"):
        lines.append(f"EXECUTION:   parallelism {ex.get('parallelism', 1)}, isolation {ex.get('isolation', 'none')}")
    if spec.get("autonomy"):
        a = _d(spec.get("autonomy"))
        earned, _ = max_autonomy(spec)
        bits = f"requested {a['requested']} / max earned {earned}" if a.get("requested") else f"max earned {earned}"
        if a.get("output_reversibility"):
            bits += f"; output {a['output_reversibility']}"
        lines.append(f"AUTONOMY:    {bits}")
    return "\n".join(lines)


def render_plain(spec):
    """One jargon-free sentence describing what the loop will do — for a human deciding whether to run it."""
    spec = _d(spec)
    g, sc, v = _d(spec.get("goal")), _d(spec.get("stop_conditions")), _d(spec.get("verifier"))
    scope, trig = _d(spec.get("scope")), _d(spec.get("trigger"))
    parts = [f"Runs {trig.get('detail') or trig.get('type') or 'on demand'}"]
    if v.get("check"):
        parts.append(f"checks that {v['check']}")
    stops = []
    if sc.get("max_iterations"):
        stops.append(f"{sc['max_iterations']} tries")
    b = _d(sc.get("budget"))
    if b.get("max_cost_usd") is not None:
        stops.append(f"${b['max_cost_usd']}")
    elif b.get("max_tokens"):
        stops.append(f"{b['max_tokens']} tokens")
    elif b.get("max_runtime_seconds"):
        stops.append(f"{b['max_runtime_seconds']}s")
    if stops:
        parts.append("stops after " + " or ".join(stops))
    if scope.get("may_touch"):
        parts.append("touches only " + ", ".join(scope["may_touch"]))
    if scope.get("must_not_touch"):
        parts.append("never " + ", ".join(scope["must_not_touch"]))
    rev = _d(spec.get("autonomy")).get("output_reversibility")
    rev_txt = {"reversible": "output is reversible (e.g. a PR you review)",
               "outward_facing": "output is OUTWARD-FACING (posts/sends) — a human should approve it",
               "irreversible": "output is IRREVERSIBLE (prod/payment/delete) — a human must own that step"}
    if rev in rev_txt:
        parts.append(rev_txt[rev])
    earned, _ = max_autonomy(spec)
    return "; ".join(parts) + f".  [max safe autonomy: {earned}]"


# ---------- CLI ----------

def _main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 2
    with open(args[0]) as f:
        spec = json.load(f)

    errors, warnings = validate(spec)

    if "--explain" in flags:
        try:
            print(render_plain(spec))
        except Exception as exc:
            print(f"(could not explain malformed spec: {exc})")

    if "--render" in flags:
        try:
            print(render(spec))
        except Exception as exc:  # a malformed spec must still surface its errors, not a traceback
            print(f"(could not render malformed spec: {exc})")
        if errors or warnings:
            print("\n--- validation ---", file=sys.stderr)

    for w in warnings:
        print(f"WARN:  {w}", file=sys.stderr)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    strict = "--strict" in flags
    if errors or (strict and warnings):
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    if "--render" not in flags:
        print(f"OK: valid loop spec ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
