"""Command-line interface for Super Looper."""

import argparse
import json
import sys

from . import __version__
from .design import build_spec, command_questions, read_answers
from .validate import max_autonomy, render, render_plain, validate


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _print_validation(errors, warnings):
    for warning in warnings:
        print(f"WARN:  {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)


def _exit_code(errors, warnings, strict):
    if errors or (strict and warnings):
        print(f"\nFAILED: {len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 1
    return 0


def cmd_questions(args):
    return command_questions(args)


def cmd_interview(args):
    answers = read_answers(args.answers) if args.answers else None
    if answers is None:
        from .design import ask_interactive

        answers = ask_interactive()
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


def cmd_validate(args):
    spec = _load_json(args.spec)
    errors, warnings = validate(spec)
    _print_validation(errors, warnings)
    rc = _exit_code(errors, warnings, args.strict)
    if rc == 0:
        print(f"OK: valid loop spec ({len(warnings)} warning(s))")
    return rc


def cmd_render(args):
    spec = _load_json(args.spec)
    errors, warnings = validate(spec)
    try:
        print(render(spec))
    except Exception as exc:
        print(f"(could not render malformed spec: {exc})")
    if errors or warnings:
        print("\n--- validation ---", file=sys.stderr)
    _print_validation(errors, warnings)
    return _exit_code(errors, warnings, args.strict)


def cmd_explain(args):
    spec = _load_json(args.spec)
    errors, warnings = validate(spec)
    try:
        print(render_plain(spec))
    except Exception as exc:
        print(f"(could not explain malformed spec: {exc})")
    if args.validate:
        _print_validation(errors, warnings)
        return _exit_code(errors, warnings, args.strict)
    return 0


def cmd_max_autonomy(args):
    spec = _load_json(args.spec)
    level, missing = max_autonomy(spec)
    payload = {"max_autonomy": level, "missing_for_more_autonomy": missing}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(level)
        for item in missing:
            print(f"- {item}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="super-looper", description="Design and validate agentic loop specs.")
    parser.add_argument("--version", action="version", version=f"super-looper {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    questions = sub.add_parser("questions", help="print the interview question keys")
    questions.set_defaults(func=cmd_questions)

    interview = sub.add_parser("interview", help="classify answers and optionally write a loop spec")
    interview.add_argument("--answers", help="JSON file with interview answers")
    interview.add_argument("--out", help="write generated loop spec here when verdict is AUTONOMOUS_LOOP")
    interview.set_defaults(func=cmd_interview)

    validate_cmd = sub.add_parser("validate", help="validate a JSON loop spec")
    validate_cmd.add_argument("spec")
    validate_cmd.add_argument("--strict", action="store_true", help="treat warnings as errors")
    validate_cmd.set_defaults(func=cmd_validate)

    render_cmd = sub.add_parser("render", help="render a JSON loop spec as the canonical text form")
    render_cmd.add_argument("spec")
    render_cmd.add_argument("--strict", action="store_true", help="treat warnings as errors")
    render_cmd.set_defaults(func=cmd_render)

    explain = sub.add_parser("explain", help="print a one-sentence plain-language preview")
    explain.add_argument("spec")
    explain.add_argument("--validate", action="store_true", help="also print validation messages and fail on errors")
    explain.add_argument("--strict", action="store_true", help="with --validate, treat warnings as errors")
    explain.set_defaults(func=cmd_explain)

    autonomy = sub.add_parser("max-autonomy", help="compute the highest earned autonomy level")
    autonomy.add_argument("spec")
    autonomy.add_argument("--json", action="store_true", help="print structured JSON")
    autonomy.set_defaults(func=cmd_max_autonomy)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
