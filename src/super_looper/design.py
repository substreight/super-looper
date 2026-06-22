#!/usr/bin/env python3
"""design_loop.py - conservative loop interview and spec compiler.

This does not run a loop. It turns interview answers into one of the skill's
verdicts, emits a discovery plan when the answers are unknown, and writes a
validated draft loop spec only when the answers are concrete enough.

Usage:
    python scripts/design_loop.py interview --answers answers.json
    python scripts/design_loop.py interview --answers answers.json --out loop.json
    python scripts/design_loop.py questions
"""

import argparse
import json
import re
import sys

from .validate import validate, max_autonomy


VERDICTS = {
    "AUTONOMOUS_LOOP",
    "DISCOVERY_REQUIRED",
    "HUMAN_IN_LOOP",
    "NOT_A_LOOP",
    "REJECT_DESIGN",
    "USE_SCHEDULER",
}

QUESTIONS = [
    ("task", "What task should run?"),
    ("recurs", "Does it recur at least weekly? (yes/no/unknown)"),
    ("deterministic_without_llm", "Could a fixed script plus the gate do this without model judgment? (yes/no)"),
    ("wrong_result_signal", "What would automatically prove a result wrong?"),
    ("self_grading", "Would the loop grade its own output with no external check? (yes/no)"),
    ("agent_can_do_end_to_end", "Can the agent finish the whole task end-to-end without handing work back? (yes/no)"),
    ("finished_state", "What finished state should be true?"),
    ("may_touch", "What may it read or edit? (comma-separated)"),
    ("must_not_touch", "What must it never touch? (comma-separated)"),
    ("unattended", "Should it run unattended, with no human in the loop each run? (yes/no)"),
    ("output_reversibility", "Is the output reversible, outward_facing, or irreversible?"),
    ("budget", "What is the max spend/runtime per run?"),
]

UNKNOWN_WORDS = {
    "", "?", "unknown", "not sure", "unsure", "unclear", "n/a", "na", "none",
    "i don't know", "i dont know", "can't answer", "cant answer", "cannot answer",
}

SUBJECTIVE_HINTS = {
    "best", "better", "good", "great", "clean", "cleaner", "compelling", "nice",
    "polished", "high quality", "beautiful", "reads well", "taste",
}

MEASURABLE = re.compile(
    r"[<>=]=?|!=|\b\d+\b|\b(exit|exits|pass|passes|fail|fails|valid|invalid|schema|"
    r"zero|count|status|code|returns?|matches?|true|false|success|error|errors|"
    r"build|builds|compile|compiles|lint|test|tests|threshold|exists?)\b",
    re.IGNORECASE,
)


def _unknown(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in UNKNOWN_WORDS
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def _truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"y", "yes", "true", "1", "weekly", "daily"}
    return bool(value)


def _list(value):
    if _unknown(value):
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _string(value, default=""):
    return default if _unknown(value) else str(value).strip()


def _slug(text):
    bits = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(bits[:5]) or "designed-loop"


def _is_subjective(text):
    low = (text or "").lower()
    return any(word in low for word in SUBJECTIVE_HINTS) and not MEASURABLE.search(low)


def _budget_obj(answers):
    budget = answers.get("budget")
    if isinstance(budget, dict):
        out = {}
        for key in ("max_tokens", "max_runtime_seconds"):
            val = budget.get(key)
            if isinstance(val, int) and val > 0:
                out[key] = val
        val = budget.get("max_cost_usd")
        if isinstance(val, (int, float)) and val >= 0:
            out["max_cost_usd"] = val
        return out
    runtime = answers.get("max_runtime_seconds")
    if isinstance(runtime, int) and runtime > 0:
        return {"max_runtime_seconds": runtime}
    cost = answers.get("max_cost_usd")
    if isinstance(cost, (int, float)) and cost >= 0:
        return {"max_cost_usd": cost}
    tokens = answers.get("max_tokens")
    if isinstance(tokens, int) and tokens > 0:
        return {"max_tokens": tokens}
    if isinstance(budget, str) and not _unknown(budget):
        text = budget.lower()
        money = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", text)
        if money:
            return {"max_cost_usd": float(money.group(1))}
        minutes = re.search(r"\b([0-9]+)\s*(min|mins|minute|minutes)\b", text)
        if minutes:
            return {"max_runtime_seconds": int(minutes.group(1)) * 60}
        seconds = re.search(r"\b([0-9]+)\s*(sec|secs|second|seconds|s)\b", text)
        if seconds:
            return {"max_runtime_seconds": int(seconds.group(1))}
        token_match = re.search(r"\b([0-9]+)\s*(token|tokens)\b", text)
        if token_match:
            return {"max_tokens": int(token_match.group(1))}
    return {}


def unknown_report(answers, missing):
    task = _string(answers.get("task"), "the proposed task")
    return {
        "verdict": "DISCOVERY_REQUIRED",
        "autonomy": "L0",
        "task": task,
        "rationale": [
            "A loop spec would require guessing at critical safety facts.",
            "Unknown answers are evidence-gathering work, not permission to automate.",
        ],
        "open_questions": missing,
        "discovery_plan": [
            "Run one watched manual attempt and record what failed.",
            "Name one bad output the future gate must reject.",
            "Build or choose the smallest tool/check that catches that bad output.",
            "Define may_touch and must_not_touch before any write-capable run.",
            "Set a runtime, token, or cost cap before retrying automation design.",
        ],
    }


def render_decision(report, spec=None):
    """Human-first verdict card for `super-looper decide`.

    The interview/compiler can still emit JSON for tooling, but the default UX
    should tell a person what happened, why, the safe autonomy level, and the next
    concrete step without requiring them to read a nested object.
    """
    verdict = report.get("verdict", "UNKNOWN")
    task = report.get("task") or "the proposed task"
    autonomy = report.get("autonomy") or report.get("max_autonomy") or "L0"
    lines = [verdict.replace("_", " ")]
    lines.append("")
    lines.append("Task:")
    lines.append(f"  {task}")
    lines.append("")
    lines.append("Safe autonomy:")
    lines.append(f"  {autonomy}")

    rationale = report.get("rationale") or []
    if rationale:
        lines.append("")
        lines.append("Why:")
        for item in rationale:
            lines.append(f"  - {item}")

    if report.get("gate"):
        lines.append("")
        lines.append("Gate:")
        lines.append(f"  {report['gate']}")

    open_questions = report.get("open_questions") or []
    if open_questions:
        lines.append("")
        lines.append("Answer before continuing:")
        for i, item in enumerate(open_questions, 1):
            lines.append(f"  {i}. {item}")

    missing = report.get("missing_for_more_autonomy") or []
    if missing:
        lines.append("")
        lines.append("To earn more autonomy:")
        for item in missing:
            lines.append(f"  - {item}")

    plan = report.get("discovery_plan") or []
    if plan:
        lines.append("")
        lines.append("Next discovery steps:")
        for i, item in enumerate(plan, 1):
            lines.append(f"  {i}. {item}")
    elif spec is not None:
        lines.append("")
        lines.append("Next:")
        lines.append("  super-looper check <loop.json>")

    alternative = report.get("alternative")
    if alternative:
        lines.append("")
        lines.append("Better path:")
        lines.append(f"  {alternative}")

    validation = report.get("validation") or {}
    errors = validation.get("errors") or []
    warnings = validation.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for item in warnings:
            lines.append(f"  ! {item}")
    if errors:
        lines.append("")
        lines.append("Errors:")
        for item in errors:
            lines.append(f"  x {item}")

    return "\n".join(lines)


def classify_answers(answers):
    """Return a verdict report. Never guesses through unknown critical fields."""
    critical = []
    if _unknown(answers.get("recurs")):
        critical.append("Does this recur at least weekly?")
    if (
        _unknown(answers.get("wrong_result_signal"))
        and _unknown(answers.get("gate_check"))
        and _unknown(answers.get("evidence"))
    ):
        critical.append("What would automatically prove a result wrong?")
    if _unknown(answers.get("finished_state")) and _unknown(answers.get("end_state")):
        critical.append("What finished state should be objectively true?")
    if not _list(answers.get("may_touch")):
        critical.append("What may the loop read or edit?")
    if not _list(answers.get("must_not_touch")):
        critical.append("What must the loop never touch?")
    if not _budget_obj(answers):
        critical.append("What hard machine-readable runtime/token/cost cap stops the run?")
    if critical:
        return unknown_report(answers, critical)

    task = _string(answers.get("task"), "the proposed task")
    gate = (_string(answers.get("gate_check"))
            or _string(answers.get("evidence"))
            or _string(answers.get("wrong_result_signal")))
    finished = _string(answers.get("finished_state")) or _string(answers.get("end_state"))

    if not _truthy(answers.get("recurs")):
        return {
            "verdict": "NOT_A_LOOP",
            "autonomy": "L0",
            "task": task,
            "rationale": ["The work does not recur often enough to repay loop setup."],
            "alternative": "Use a one-shot prompt or interactive session.",
        }

    if _truthy(answers.get("deterministic_without_llm")):
        return {
            "verdict": "USE_SCHEDULER",
            "autonomy": "L0",
            "task": task,
            "rationale": ["A fixed script plus the gate would do the job without model judgment."],
            "alternative": "Use cron, Task Scheduler, or CI scheduling around the deterministic script.",
        }

    if _is_subjective(gate) or _is_subjective(finished):
        return {
            "verdict": "HUMAN_IN_LOOP",
            "autonomy": "L1",
            "task": task,
            "rationale": ["The pass condition is subjective, so a human remains the real gate."],
            "alternative": "Use the loop as a draft generator and keep human approval at verify/publish.",
        }

    if _truthy(answers.get("self_grading")):
        return {
            "verdict": "REJECT_DESIGN",
            "autonomy": "L0",
            "task": task,
            "rationale": ["The maker grading its own output is off the verifier ladder."],
            "alternative": "Add a tool gate, independent model checker, or human gate.",
        }

    if answers.get("output_reversibility") in {"outward_facing", "irreversible"} and _truthy(answers.get("unattended")):
        return {
            "verdict": "HUMAN_IN_LOOP",
            "autonomy": "L1",
            "task": task,
            "rationale": ["The output is outward-facing or irreversible, so a human must own that step."],
            "alternative": "Generate drafts or PRs, then require human approval before publish/write/delete.",
        }

    answered_end_to_end = answers.get("agent_can_do_end_to_end")
    if not _unknown(answered_end_to_end) and not _truthy(answered_end_to_end):
        return {
            "verdict": "HUMAN_IN_LOOP",
            "autonomy": "L1",
            "task": task,
            "rationale": ["The agent cannot complete the task end-to-end without handing work back."],
            "alternative": "Automate the checkable sub-step and keep the rest interactive.",
        }

    explicit_rung = _string(answers.get("gate_rung"))
    if explicit_rung:
        rung = explicit_rung
    elif MEASURABLE.search(gate):
        rung = "tool"
    else:
        # A grammatical but non-measurable gate with no explicit checker named is not
        # concrete enough to mint an autonomous loop. Treat it like "I don't know":
        # gather evidence and name a gate that can actually fail the work.
        return unknown_report(answers, [
            "A concrete gate that can actually fail the work: name a tool/threshold/exit "
            "check, or set gate_rung to an explicit independent checker. "
            f"{gate!r} has no measurable signal, so automating against it would be guessing."])
    report = {
        "verdict": "AUTONOMOUS_LOOP",
        "autonomy": "L2",
        "task": task,
        "rationale": [
            "The task recurs and has an automatic verifier candidate.",
            "Generate a spec, validate it, prove one manual pass, then raise autonomy only as earned.",
        ],
        "gate_rung": rung,
        "gate": gate,
    }
    return report


def build_spec(answers):
    report = classify_answers(answers)
    if report["verdict"] != "AUTONOMOUS_LOOP":
        return None, report

    task = _string(answers.get("task"), "Designed loop")
    gate = (_string(answers.get("gate_check"))
            or _string(answers.get("evidence"))
            or _string(answers.get("wrong_result_signal")))
    end_state = _string(answers.get("finished_state")) or _string(answers.get("end_state")) or gate
    may_touch = _list(answers.get("may_touch"))
    must_not_touch = _list(answers.get("must_not_touch"))
    budget = _budget_obj(answers) or {"max_runtime_seconds": 900}
    rung = report.get("gate_rung", "tool")
    unattended = _truthy(answers.get("unattended"))
    reversibility = answers.get("output_reversibility") or "reversible"
    proven_manual = _truthy(answers.get("proven_manual_pass"))

    requested = "L1"
    if budget and must_not_touch and rung in {"tool", "independent_model"}:
        requested = "L2"
    if (
        requested == "L2"
        and rung == "tool"
        and unattended
        and reversibility == "reversible"
        and proven_manual
        and _truthy(answers.get("end_to_end", False))
    ):
        requested = "L3"

    spec = {
        "name": _slug(task),
        "goal": {
            "end_state": end_state,
            "evidence": _string(answers.get("evidence")) or gate,
            "constraints": _list(answers.get("constraints")),
            "budget": _string(answers.get("budget_summary")) or "bounded by stop_conditions.budget",
        },
        "scope": {
            "may_touch": may_touch,
            "must_not_touch": must_not_touch,
        },
        "loop_shape": answers.get("loop_shape") or "completion",
        "trigger": {
            "type": answers.get("trigger_type") or ("schedule" if unattended else "manual"),
            "detail": _string(answers.get("cadence")) or ("manual dry run" if not unattended else "scheduled"),
            "unattended": unattended,
        },
        "iteration": [
            "load durable context and progress from disk",
            "choose the single highest-impact open item",
            "make the smallest change; on retry, change approach",
            "run the verifier and write progress back to disk",
        ],
        "verifier": {
            "rung": rung,
            "check": gate,
            "independent": rung in {"tool", "independent_model"},
            "end_to_end": _truthy(answers.get("end_to_end", False)),
        },
        "state": {
            "architecture": answers.get("state_architecture") or "fresh_restart",
            "on_disk": True,
            "durable_progress": _list(answers.get("durable_progress")) or ["state/progress.jsonl"],
        },
        "stop_conditions": {
            "success": gate,
            "max_iterations": int(answers.get("max_iterations") or 3),
            "budget": budget,
            "no_progress": {
                "signal": _string(answers.get("no_progress_signal")) or "same verifier failure",
                "repeats": int(answers.get("no_progress_repeats") or 2),
            },
        },
        "on_stop": _string(answers.get("on_stop")) or "summarize changes and open gaps; do not claim success unless the verifier passed",
        "report": {"destination": _string(answers.get("report_destination"), "stdout")},
        "maker": {
            "model": _string(answers.get("maker_model"), "cheap"),
            "effort": _string(answers.get("maker_effort"), "low"),
        },
        "autonomy": {
            "requested": requested,
            "output_reversibility": reversibility,
            "proven_manual_pass": proven_manual,
        },
        "economics": {
            "billing": answers.get("billing") or "unknown",
            "proven_cheap": _truthy(answers.get("proven_cheap")),
        },
    }

    errors, warnings = validate(spec)
    level, missing = max_autonomy(spec)
    report["autonomy"] = requested
    report["max_autonomy"] = level
    report["validation"] = {"errors": errors, "warnings": warnings}
    if missing:
        report["missing_for_more_autonomy"] = missing
    return spec, report


def read_answers(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def ask_interactive():
    answers = {}
    for key, prompt in QUESTIONS:
        answers[key] = input(prompt + " ").strip()
    return answers


def command_questions(_args):
    for key, prompt in QUESTIONS:
        print(f"{key}: {prompt}")
    return 0


def command_interview(args):
    answers = read_answers(args.answers) if args.answers else ask_interactive()
    spec, report = build_spec(answers)
    result = {"report": report}
    if spec is not None:
        result["spec"] = spec
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(spec, f, indent=2)
                f.write("\n")
    print(json.dumps(result, indent=2))
    return 1 if report.get("validation", {}).get("errors") else 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("questions", help="print the interview question keys")
    q.set_defaults(func=command_questions)

    interview = sub.add_parser("interview", help="classify answers and optionally write a loop spec")
    interview.add_argument("--answers", help="JSON file with interview answers")
    interview.add_argument("--out", help="write generated loop spec here when verdict is AUTONOMOUS_LOOP")
    interview.set_defaults(func=command_interview)

    args = parser.parse_args(argv[1:])
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
