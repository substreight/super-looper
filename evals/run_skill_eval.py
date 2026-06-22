#!/usr/bin/env python3
"""run_skill_eval.py - run the ACTUAL skill (SKILL.md) blind over each eval scenario.

This is the live half of the skill's own gate. For every scenario it sends SKILL.md plus
the scenario prompt to a model in a FRESH context (no cross-scenario leakage, no answer key),
captures a {verdict, rationale}, and writes a results file that score_eval.py then grades.
Unlike a frozen results file, this can actually catch a skill regression.

Deterministic logic (build_messages / parse_response / run_eval) is dependency-free and unit
-tested. The Anthropic call is imported lazily so this module loads without the SDK installed.

Usage:
    python evals/run_skill_eval.py --skill SKILL.md --scenarios evals/scenarios.jsonl \
        --out results.live.jsonl --model claude-opus-4-8
    python evals/score_eval.py evals/scenarios.jsonl results.live.jsonl --min 0.8
"""
import argparse
import json
import re
import sys

VERDICTS = [
    "AUTONOMOUS_LOOP", "DISCOVERY_REQUIRED", "HUMAN_IN_LOOP",
    "NOT_A_LOOP", "REJECT_DESIGN", "USE_SCHEDULER",
]

DEFAULT_MODEL = "claude-opus-4-8"


def build_messages(skill_text, prompt):
    """Return (system, user). BLIND by construction: only the scenario prompt is included --
    never the scenario's expected_verdict / acceptable_verdicts / must_mention."""
    system = skill_text
    user = (
        "Task:\n" + (prompt or "").strip() + "\n\n"
        "Apply the skill above and decide the single best verdict for this task. "
        "Respond with ONLY a JSON object on one line, no prose:\n"
        '{"verdict": "<one of ' + ", ".join(VERDICTS) + '>", '
        '"rationale": "<one to three sentences naming why>"}'
    )
    return system, user


def parse_response(text):
    """Extract {verdict, rationale} from model output; tolerate prose / code fences."""
    text = text or ""
    for blob in reversed(re.findall(r"\{[^{}]*\}", text, re.DOTALL)):
        try:
            obj = json.loads(blob)
        except ValueError:
            continue
        verdict = str(obj.get("verdict", "")).upper().strip()
        if verdict:
            return {"verdict": verdict, "rationale": str(obj.get("rationale", "")).strip()}
    # Fallback: a bare verdict token somewhere in the text.
    upper = text.upper()
    for v in VERDICTS:
        if v in upper:
            return {"verdict": v, "rationale": text.strip()[:500]}
    return {"verdict": "", "rationale": text.strip()[:500]}


def run_eval(skill_text, scenarios, ask):
    """ask(system, user) -> model text. Returns [{id, verdict, rationale}], one per scenario,
    each from a fresh `ask` call (blind: only build_messages output is sent)."""
    results = []
    for scenario in scenarios:
        system, user = build_messages(skill_text, scenario.get("prompt", ""))
        parsed = parse_response(ask(system, user))
        results.append({"id": scenario.get("id"), "verdict": parsed["verdict"],
                        "rationale": parsed["rationale"]})
    return results


def _anthropic_ask(model, max_tokens=1024):
    """Build a real ask(system, user) backed by the Anthropic API. Imported lazily so the
    module (and its unit tests) load with no SDK and no API key."""
    import anthropic  # noqa: F401

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

    def ask(system, user):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", None) == "text")

    return ask


def _load_scenarios(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, help="path to SKILL.md")
    parser.add_argument("--scenarios", required=True, help="scenarios.jsonl (answer key NOT shown to the model)")
    parser.add_argument("--out", required=True, help="write the live results jsonl here")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args(argv[1:])

    with open(args.skill, encoding="utf-8") as f:
        skill_text = f.read()
    scenarios = _load_scenarios(args.scenarios)

    ask = _anthropic_ask(args.model)
    results = run_eval(skill_text, scenarios, ask)

    with open(args.out, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(results)} verdicts to {args.out} (model {args.model})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
