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
from importlib.resources import files


def _load_schema():
    """Load the schema across package and source-tree layouts."""
    try:
        resource = files("super_looper.resources").joinpath("loop-spec.schema.json")
        if resource.is_file():
            with resource.open(encoding="utf-8") as f:
                return json.load(f)
    except (ModuleNotFoundError, OSError, ValueError):
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "resources", "loop-spec.schema.json"),
        os.path.join(here, "loop-spec.schema.json"),
        os.path.join(here, "..", "..", "schemas", "loop-spec.schema.json"),
    ):
        if os.path.exists(candidate):
            with open(candidate, encoding="utf-8") as f:
                return json.load(f)
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


# Conservative signals that a loop runs third-party code (so it should declare execution.untrusted).
# Deliberately narrow -- dependency-install / external-clone, NOT merely "runs tests" (your own tests
# are trusted), to avoid nagging trusted in-repo loops.
_UNTRUSTED_HINTS = (
    "pip install", "pip3 install", "uv pip", "poetry install", "npm install", "npm ci",
    "yarn install", "pnpm install", "bundle install", "gem install", "cargo build",
    "cargo install", "go install", "git clone", "make install", "postinstall", "npx ",
)


def _coherent_policy(policy):
    """An execution policy is coherent iff it actually isolates: no host credentials,
    no network during the graded run, and only allowlisted artifacts copied back."""
    policy = _d(policy)
    net = _d(policy.get("network"))
    return (policy.get("host_credentials") == "none"
            and net.get("verification") == "off"
            and policy.get("artifacts") == "allowlist")


def _looks_untrusted(spec):
    spec = _d(spec)
    blobs = [s.lower() for s in (spec.get("iteration") or []) if isinstance(s, str)]
    check = _d(spec.get("verifier")).get("check")
    if isinstance(check, str):
        blobs.append(check.lower())
    text = " ".join(blobs)
    return any(hint in text for hint in _UNTRUSTED_HINTS)


_AUTONOMY_ORDER = ["L0", "L1", "L2", "L3"]


def max_autonomy(spec):
    """Compute the highest autonomy level a loop has EARNED, plus what's missing to go higher.

    Returns (level, missing): level in L0..L3, missing = the gaps blocking the next level.
    Autonomy is earned, never chosen. L2 needs a real automatic gate plus a budget
    cap and scope fence. L3 additionally needs an unattended trigger, a rung-1
    end-to-end tool gate, explicit reversible output, and a proven manual pass.
    Pure; reads the same fields the semantic checks read.
    """
    spec = _d(spec)
    verifier = _d(spec.get("verifier"))
    scope = _d(spec.get("scope"))
    sc = _d(spec.get("stop_conditions"))
    trigger = _d(spec.get("trigger"))
    autonomy = _d(spec.get("autonomy"))
    reversibility = autonomy.get("output_reversibility")
    rung = verifier.get("rung")

    # The gate rung sets the hard ceiling.
    if rung in ("self", None):
        return "L1", ["a real gate (verifier.rung 'tool' or 'independent_model' — self/none can't run unsupervised)"]
    if rung == "human":
        return "L1", ["an automatic gate (a human gate is human-in-the-loop by definition)"]

    # A taste/weasel gate can't license unattended autonomy: the maker can argue its way
    # past it, so it won't reliably fail bad work. Gate quality stays advisory (a warning)
    # at L0/L1, but here -- where autonomy is on the line -- it caps the earned ceiling.
    check = verifier.get("check") or ""
    end_state = _d(spec.get("goal")).get("end_state") or ""
    weasel = _weasel(check) or _weasel(end_state)
    if weasel:
        return "L1", [f"a gate that isn't a taste judgment ({weasel!r}); state it so a tool or a "
                      "different model can decide it (exit code, threshold, schema, match)"]

    # rung is 'tool' or 'independent_model': L2 is reachable only with guardrails.
    l2_missing = []
    if not sc.get("budget"):
        l2_missing.append("a budget cap (stop_conditions.budget)")
    if not scope.get("must_not_touch"):
        l2_missing.append("a blast-radius fence (scope.must_not_touch)")
    if l2_missing:
        return "L1", l2_missing

    # L2 is the ceiling for independent model gates.
    if rung != "tool":
        return "L2", ["a rung-1 tool gate on the deliverable (independent_model tops out at L2)"]

    # L3 needs every unattended guardrail, explicitly stated.
    l3_missing = []
    if trigger.get("type") is None or trigger.get("unattended") is not True:
        l3_missing.append("an explicit unattended trigger (trigger.type plus trigger.unattended=true)")
    if verifier.get("end_to_end") is not True:
        l3_missing.append("an end-to-end tool gate on the real deliverable (verifier.end_to_end=true)")
    if reversibility != "reversible":
        if reversibility is None:
            l3_missing.append("explicit reversible output (autonomy.output_reversibility='reversible')")
        else:
            l3_missing.append(f"reversible output (it's {reversibility} — a human must own the irreversible step)")
    if autonomy.get("proven_manual_pass") is not True:
        l3_missing.append("a proven manual pass (autonomy.proven_manual_pass=true)")
    return ("L3", []) if not l3_missing else ("L2", l3_missing)


ENUMS = {
    ("loop_shape",): ["completion", "cadence"],
    ("verifier", "rung"): ["tool", "independent_model", "human", "self"],
    ("state", "architecture"): ["fresh_restart", "compaction"],
    ("trigger", "type"): ["schedule", "event", "manual"],
    ("execution", "isolation"): ["none", "worktree", "sandbox"],
    ("execution", "policy", "host_credentials"): ["none", "scoped"],
    ("execution", "policy", "artifacts"): ["allowlist", "all"],
    ("execution", "policy", "network", "setup"): ["on", "off"],
    ("execution", "policy", "network", "verification"): ["on", "off"],
    ("economics", "billing"): ["prepaid", "metered", "unknown"],
    ("autonomy", "requested"): ["L0", "L1", "L2", "L3"],
    ("autonomy", "output_reversibility"): ["reversible", "outward_facing", "irreversible"],
}


# ---------- structural validation ----------

# Allowed keys per object, mirroring schemas/loop-spec.schema.json's
# additionalProperties:false so the zero-dependency checker is exactly as strict
# as the JSON Schema path. ``meta`` is intentionally open (schema extension point).
# Keep in sync with the schema; test_schemas_in_sync + the tests below guard drift.
_ALLOWED_KEYS = {
    (): frozenset({"name", "goal", "scope", "loop_shape", "trigger", "iteration",
                   "verifier", "state", "stop_conditions", "on_stop", "report",
                   "maker", "checker", "execution", "economics", "autonomy", "meta"}),
    ("goal",): frozenset({"end_state", "evidence", "constraints", "budget"}),
    ("scope",): frozenset({"may_touch", "must_not_touch"}),
    ("trigger",): frozenset({"type", "detail", "unattended"}),
    ("verifier",): frozenset({"rung", "check", "independent", "end_to_end"}),
    ("state",): frozenset({"architecture", "on_disk", "durable_context", "durable_progress"}),
    ("stop_conditions",): frozenset({"success", "max_iterations", "budget", "no_progress"}),
    ("stop_conditions", "budget"): frozenset({"max_tokens", "max_cost_usd", "max_runtime_seconds"}),
    ("stop_conditions", "no_progress"): frozenset({"signal", "repeats"}),
    ("report",): frozenset({"destination"}),
    ("maker",): frozenset({"model", "effort"}),
    ("checker",): frozenset({"model", "effort"}),
    ("execution",): frozenset({"parallelism", "isolation", "untrusted", "policy"}),
    ("execution", "policy"): frozenset({"host_credentials", "network", "artifacts"}),
    ("execution", "policy", "network"): frozenset({"setup", "verification"}),
    ("economics",): frozenset({"billing", "proven_cheap"}),
    ("autonomy",): frozenset({"requested", "output_reversibility", "proven_manual_pass"}),
}


def _check_unknown_keys(spec):
    """Reject object keys the schema forbids (additionalProperties: false).

    A misspelled field (``must_not_tuch``, ``end_stat``) is otherwise silently
    ignored, which is the blindest spot of a hand-written checker: the loop runs
    as if the safety field were absent. One mechanism covers budget/policy/network
    and every other object, so there is a single source of truth to keep in sync.
    """
    errors = []
    for path, allowed in _ALLOWED_KEYS.items():
        obj = spec
        for p in path:
            obj = obj.get(p) if isinstance(obj, dict) else None
        if not isinstance(obj, dict):
            continue
        where = ".".join(path) if path else "<root>"
        for key in obj:
            if key not in allowed:
                errors.append(
                    f"{where} has unknown key {key!r} (allowed: {sorted(allowed)}). "
                    "A misspelled field is silently ignored; fix the typo.")
    return errors


def _builtin_structural(spec):
    """Structural check used when jsonschema isn't installed.

    Keep this close to schemas/loop-spec.schema.json for the fields the semantic
    lint relies on. It intentionally stays small, but it must catch bad shapes
    and scalar types so validate() remains a safe harness gate with no deps.
    """
    errors = []
    if not isinstance(spec, dict):
        return [f"spec must be a JSON object, got {type(spec).__name__}"]

    required_top = ["name", "goal", "scope", "loop_shape", "verifier", "state",
                    "stop_conditions", "on_stop"]
    for k in required_top:
        if k not in spec:
            errors.append(f"missing required field: {k}")

    def kind(obj):
        return type(obj).__name__

    def obj_at(path):
        obj = spec
        for p in path:
            obj = obj.get(p) if isinstance(obj, dict) else None
        return obj

    def expect_obj(path):
        obj = obj_at(path)
        if obj is not None and not isinstance(obj, dict):
            errors.append(f"{'.'.join(path)} must be an object, got {kind(obj)}")
        return obj if isinstance(obj, dict) else None

    def expect_str(obj, path, required=False):
        key = path[-1]
        if not isinstance(obj, dict) or key not in obj:
            if required:
                errors.append(f"missing required field: {'.'.join(path)}")
            return
        val = obj.get(key)
        if not isinstance(val, str) or val == "":
            errors.append(f"{'.'.join(path)} must be a non-empty string")

    def expect_bool(obj, path, required=False):
        key = path[-1]
        if not isinstance(obj, dict) or key not in obj:
            if required:
                errors.append(f"missing required field: {'.'.join(path)}")
            return
        if not isinstance(obj.get(key), bool):
            errors.append(f"{'.'.join(path)} must be a boolean")

    def expect_int(obj, path, required=False, minimum=None):
        key = path[-1]
        if not isinstance(obj, dict) or key not in obj:
            if required:
                errors.append(f"missing required field: {'.'.join(path)}")
            return
        val = obj.get(key)
        if not isinstance(val, int) or isinstance(val, bool):
            errors.append(f"{'.'.join(path)} must be an integer")
            return
        if minimum is not None and val < minimum:
            errors.append(f"{'.'.join(path)} must be >= {minimum}")

    def expect_list(obj, path, required=False, min_items=0):
        key = path[-1]
        if not isinstance(obj, dict) or key not in obj:
            if required:
                errors.append(f"missing required field: {'.'.join(path)}")
            return
        val = obj.get(key)
        if not isinstance(val, list):
            errors.append(f"{'.'.join(path)} must be an array")
            return
        if len(val) < min_items:
            errors.append(f"{'.'.join(path)} must contain at least {min_items} item(s)")
        for i, item in enumerate(val):
            if not isinstance(item, str):
                errors.append(f"{'.'.join(path)}[{i}] must be a string")

    def req(obj, path, keys):
        for k in keys:
            if not isinstance(obj, dict) or k not in obj or obj.get(k) in (None, "", [], {}):
                errors.append(f"missing/empty required field: {path}.{k}")

    for top in ("goal", "scope", "verifier", "state", "stop_conditions"):
        expect_obj((top,))

    expect_str(spec, ("name",), required="name" in spec)
    expect_str(spec, ("loop_shape",), required="loop_shape" in spec)
    expect_str(spec, ("on_stop",), required="on_stop" in spec)

    goal = expect_obj(("goal",))
    if goal is not None:
        req(goal, "goal", ["end_state", "evidence", "budget"])
        expect_str(goal, ("goal", "end_state"), required=True)
        expect_str(goal, ("goal", "evidence"), required=True)
        expect_str(goal, ("goal", "budget"), required=True)
        if "constraints" not in goal:
            errors.append("missing required field: goal.constraints (use [] if none, deliberately)")
        else:
            expect_list(goal, ("goal", "constraints"))

    scope = expect_obj(("scope",))
    if scope is not None:
        if not scope.get("may_touch"):
            errors.append("missing/empty required field: scope.may_touch")
        expect_list(scope, ("scope", "may_touch"), required=True, min_items=1)
        expect_list(scope, ("scope", "must_not_touch"))

    verifier = expect_obj(("verifier",))
    if verifier is not None:
        req(verifier, "verifier", ["rung", "check"])
        expect_str(verifier, ("verifier", "rung"), required=True)
        expect_str(verifier, ("verifier", "check"), required=True)
        expect_bool(verifier, ("verifier", "independent"))
        expect_bool(verifier, ("verifier", "end_to_end"))

    state = expect_obj(("state",))
    if state is not None:
        if "on_disk" not in state:
            errors.append("missing required field: state.on_disk")
        if "architecture" not in state:
            errors.append("missing required field: state.architecture")
        expect_str(state, ("state", "architecture"), required="architecture" in state)
        expect_bool(state, ("state", "on_disk"), required="on_disk" in state)
        expect_list(state, ("state", "durable_context"))
        expect_list(state, ("state", "durable_progress"))

    sc = expect_obj(("stop_conditions",))
    if sc is not None:
        # success is the finish line of a completion loop; cadence loops run open-ended.
        required_sc = ["success", "max_iterations"] if spec.get("loop_shape") == "completion" \
            else ["max_iterations"]
        req(sc, "stop_conditions", required_sc)
        expect_str(sc, ("stop_conditions", "success"), required="success" in required_sc)
        expect_int(sc, ("stop_conditions", "max_iterations"), required=True, minimum=1)
        if not isinstance(sc.get("no_progress"), dict):
            errors.append("missing required field: stop_conditions.no_progress")
        else:
            req(sc["no_progress"], "stop_conditions.no_progress", ["signal", "repeats"])
            expect_str(sc["no_progress"], ("stop_conditions", "no_progress", "signal"), required=True)
            expect_int(sc["no_progress"], ("stop_conditions", "no_progress", "repeats"),
                       required=True, minimum=2)
        if "budget" in sc:
            budget = sc.get("budget")
            if not isinstance(budget, dict) or not budget:
                errors.append("stop_conditions.budget must be a non-empty object")
            else:
                for key in ("max_tokens", "max_runtime_seconds"):
                    if key in budget:
                        expect_int(budget, ("stop_conditions", "budget", key), minimum=1)
                if "max_cost_usd" in budget:
                    val = budget.get("max_cost_usd")
                    if not isinstance(val, (int, float)) or isinstance(val, bool) or val < 0:
                        errors.append("stop_conditions.budget.max_cost_usd must be a number >= 0")

    trigger = expect_obj(("trigger",))
    if trigger is not None:
        expect_str(trigger, ("trigger", "type"), required=True)
        expect_str(trigger, ("trigger", "detail"))
        expect_bool(trigger, ("trigger", "unattended"))

    execution = expect_obj(("execution",))
    if execution is not None:
        expect_int(execution, ("execution", "parallelism"), minimum=1)
        expect_str(execution, ("execution", "isolation"))
        expect_bool(execution, ("execution", "untrusted"))
        policy = expect_obj(("execution", "policy"))
        if policy is not None:
            expect_str(policy, ("execution", "policy", "host_credentials"))
            expect_str(policy, ("execution", "policy", "artifacts"))
            net = expect_obj(("execution", "policy", "network"))
            if net is not None:
                expect_str(net, ("execution", "policy", "network", "setup"))
                expect_str(net, ("execution", "policy", "network", "verification"))

    economics = expect_obj(("economics",))
    if economics is not None:
        expect_str(economics, ("economics", "billing"))
        expect_bool(economics, ("economics", "proven_cheap"))

    autonomy = expect_obj(("autonomy",))
    if autonomy is not None:
        expect_str(autonomy, ("autonomy", "requested"))
        expect_str(autonomy, ("autonomy", "output_reversibility"))
        expect_bool(autonomy, ("autonomy", "proven_manual_pass"))

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

    # unknown keys in any object (mirrors the schema's additionalProperties:false)
    errors.extend(_check_unknown_keys(spec))
    return errors


def _structural(spec):
    schema = _load_schema()
    if schema is not None:
        try:
            import jsonschema  # type: ignore
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
    parallelism = execution.get("parallelism", 1)
    if not isinstance(parallelism, int) or isinstance(parallelism, bool):
        parallelism = 1
    if parallelism > 1:
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

    # Untrusted execution must declare a coherent isolation policy before it can run.
    # super-looper validates the requirement; the user's own sandbox enforces it -- it is
    # an error once the loop will actually run (>= L1 or a trigger), a warning at L0.
    requested_level = _d(spec.get("autonomy")).get("requested")
    will_run = (requested_level in ("L1", "L2", "L3")) or bool(trigger.get("type")) or unattended
    if execution.get("untrusted") is True:
        if not _coherent_policy(execution.get("policy")):
            msg = ("execution.untrusted is true but there's no coherent isolation policy "
                   "(execution.policy needs host_credentials='none', network.verification='off', "
                   "artifacts='allowlist'). super-looper doesn't run the loop -- declare where it "
                   "runs safely and hand the spec to your own isolated runner.")
            (errors if will_run else warnings).append(msg)
    elif _looks_untrusted(spec):
        warnings.append("this loop appears to install or run third-party code; set "
                        "execution.untrusted and declare an isolation policy (execution.policy) if so.")

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


def render_check(spec, errors=None, warnings=None):
    """Human-first verdict card for `super-looper check`.

    Combines validation status, the plain-English behavior, and the autonomy
    verdict (requested vs max earned, and what's missing to go higher) into one
    glanceable block. Pure: callers pass in the validate() result so this never
    re-validates or raises on a malformed spec.
    """
    spec = _d(spec)
    errors = list(errors or [])
    warnings = list(warnings or [])
    lines = []

    status = "CHECK FAILED" if errors else ("CHECK PASSED (with warnings)" if warnings else "CHECK PASSED")
    lines.append(status)
    name = spec.get("name")
    if name:
        lines.append("")
        lines.append("Loop:")
        lines.append(f"  {name}")

    lines.append("")
    lines.append("Plain-English behavior:")
    try:
        lines.append(f"  {render_plain(spec)}")
    except Exception as exc:  # malformed spec must still produce a card, not a traceback
        lines.append(f"  (could not summarize malformed spec: {exc})")

    requested = _d(spec.get("autonomy")).get("requested")
    earned, missing = max_autonomy(spec)
    lines.append("")
    lines.append("Autonomy:")
    if requested:
        ok = "ok" if requested <= earned else "TOO HIGH"
        lines.append(f"  requested:  {requested} ({ok})")
    lines.append(f"  max safe:   {earned}")
    if missing:
        lines.append("  to earn more autonomy, add:")
        for item in missing:
            lines.append(f"    - {item}")
    else:
        lines.append("  nothing blocks the next level")

    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ! {w}")
    if errors:
        lines.append("")
        lines.append("Errors (fix before running):")
        for e in errors:
            lines.append(f"  x {e}")

    return "\n".join(lines)


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
