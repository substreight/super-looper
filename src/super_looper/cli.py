"""Command-line interface for Super Looper."""

import argparse
import json
import sys

from . import __version__
from .case_study import (
    CaseStudyError,
    create_manifest,
    design_case_study,
    render_report,
    resolve_verifier,
    run_case_study,
    simulate_shadow_verifier,
    verify_run,
    write_reports,
)
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


def cmd_case_study_init(args):
    try:
        result = create_manifest(
            args.out,
            args.repo,
            issue=args.issue,
            name=args.name,
            answers=args.answers,
            verifier=args.verifier,
            may_touch=args.may_touch,
            must_not_touch=args.must_not_touch,
            max_runtime_seconds=args.max_runtime_seconds,
        )
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_case_study_design(args):
    try:
        result = design_case_study(args.manifest)
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    report = result.get("report", {})
    return 1 if report.get("validation", {}).get("errors") else 0


def cmd_case_study_run(args):
    try:
        result = run_case_study(
            args.manifest,
            args.repo_path,
            run_id=args.run_id,
            skip_verifier=args.skip_verifier,
        )
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    summary = result.get("summary", {})
    if args.strict and not summary.get("ready_for_pr_claim"):
        return 1
    return 0


def cmd_case_study_simulate_verifier(args):
    try:
        result = simulate_shadow_verifier(
            args.manifest,
            args.repo_path,
            template=args.template,
            run_id=args.run_id,
        )
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    summary = result.get("summary", {})
    if args.strict and not summary.get("ready_for_shadow_report"):
        return 1
    return 0


def cmd_case_study_resolve_verifier(args):
    try:
        result = resolve_verifier(
            args.manifest,
            args.repo_path,
            template=args.template,
            shadow=not args.no_shadow,
            run_id=args.run_id,
        )
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    summary = result.get("summary", {})
    if args.strict:
        if summary.get("evidence_level") == "shadow":
            return 0 if summary.get("ready_for_shadow_report") else 1
        return 0 if summary.get("ready_for_pr_claim") else 1
    return 0


def cmd_case_study_verify(args):
    result = verify_run(args.run_dir)
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed") else 1


def cmd_case_study_report(args):
    if args.print_report:
        print(render_report(args.run_dir, args.for_audience))
        return 0
    audience = "all" if args.for_audience == "all" else args.for_audience
    outputs = write_reports(args.run_dir, audience)
    print(json.dumps(outputs, indent=2))
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

    case = sub.add_parser("case-study", help="create, run, and report real-repo loop case studies")
    case_sub = case.add_subparsers(dest="case_command", required=True)

    case_init = case_sub.add_parser("init", help="create a case-study manifest directory")
    case_init.add_argument("--repo", required=True, help="target repository URL or name")
    case_init.add_argument("--out", required=True, help="directory to create")
    case_init.add_argument("--issue", help="issue URL or identifier")
    case_init.add_argument("--name", help="case-study name")
    case_init.add_argument("--answers", help="existing answers JSON to copy into the case study")
    case_init.add_argument("--verifier", action="append", default=[], help="verifier command; repeat for multiple")
    case_init.add_argument("--may-touch", action="append", default=[], help="allowed path or comma list; repeatable")
    case_init.add_argument("--must-not-touch", action="append", default=[], help="forbidden path or comma list; repeatable")
    case_init.add_argument("--max-runtime-seconds", type=int, default=1800, help="overall verifier runtime budget")
    case_init.set_defaults(func=cmd_case_study_init)

    case_design = case_sub.add_parser("design", help="compile answers into a loop spec and design report")
    case_design.add_argument("manifest", help="case-study manifest path or directory")
    case_design.set_defaults(func=cmd_case_study_design)

    case_run = case_sub.add_parser("run", help="run verifier commands and write reproducible artifacts")
    case_run.add_argument("manifest", help="case-study manifest path or directory")
    case_run.add_argument("--repo-path", required=True, help="local checkout of the target repository")
    case_run.add_argument("--run-id", help="stable run directory name; defaults to UTC timestamp")
    case_run.add_argument("--skip-verifier", action="store_true", help="write repo/scope artifacts without running verifier")
    case_run.add_argument("--strict", action="store_true", help="exit nonzero unless verifier and scope both pass")
    case_run.set_defaults(func=cmd_case_study_run)

    case_shadow = case_sub.add_parser("simulate-verifier", help="generate and run a shadow verifier without modifying the checkout")
    case_shadow.add_argument("manifest", help="case-study manifest path or directory")
    case_shadow.add_argument("--repo-path", required=True, help="local checkout of the target repository")
    case_shadow.add_argument("--template", default="python-ast-corpus", choices=["python-ast-corpus"], help="shadow verifier template")
    case_shadow.add_argument("--run-id", help="stable run directory name; defaults to UTC timestamp")
    case_shadow.add_argument("--strict", action="store_true", help="exit nonzero unless shadow verifier and scope both pass")
    case_shadow.set_defaults(func=cmd_case_study_simulate_verifier)

    case_resolve = case_sub.add_parser("resolve-verifier", help="run confirmed verifier or fall back to shadow by default")
    case_resolve.add_argument("manifest", help="case-study manifest path or directory")
    case_resolve.add_argument("--repo-path", required=True, help="local checkout of the target repository")
    case_resolve.add_argument("--template", default="python-ast-corpus", choices=["python-ast-corpus"], help="shadow verifier template when fallback is needed")
    case_resolve.add_argument("--run-id", help="stable run directory name; defaults to UTC timestamp")
    case_resolve.add_argument("--no-shadow", action="store_true", help="do not generate a shadow verifier when the declared gate is missing")
    case_resolve.add_argument("--strict", action="store_true", help="exit nonzero unless the selected verifier path passes")
    case_resolve.set_defaults(func=cmd_case_study_resolve_verifier)

    case_verify = case_sub.add_parser("verify", help="check a run directory for reportable success")
    case_verify.add_argument("run_dir", help="case-study run directory")
    case_verify.set_defaults(func=cmd_case_study_verify)

    case_report = case_sub.add_parser("report", help="render maintainer or PR markdown from a run directory")
    case_report.add_argument("run_dir", help="case-study run directory")
    case_report.add_argument("--for", dest="for_audience", choices=["maintainer", "pr", "all"], default="maintainer")
    case_report.add_argument("--print", dest="print_report", action="store_true", help="print report markdown instead of writing files")
    case_report.set_defaults(func=cmd_case_study_report)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
