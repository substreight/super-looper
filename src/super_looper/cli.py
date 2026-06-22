"""Command-line interface for Super Looper."""

import argparse
import json
import os
import sys

from . import __version__
from .design import build_spec, command_questions, read_answers
from .validate import max_autonomy, render, render_plain, validate

# Perimeter subsystems -- the case-study harness, the remote-runner transport, and the
# repo-audit adapter -- are imported LAZILY inside their own handlers so the minimal path
# (validate / run / explain / max-autonomy / interview) never loads them.


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, payload):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def _profile_value(profile, key, fallback=None):
    value = profile.get(key, fallback)
    if value == "":
        return fallback
    return value


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


def cmd_run(args):
    """Drive a validated loop's deterministic skeleton. The driver is pure; THIS handler
    is the caller that owns the effects -- it runs your --propose/--verify shell commands
    and persists state. super-looper does not own the model or the sandbox."""
    import os as _os
    import subprocess
    from .runtime import FileStore, run_loop

    spec = _load_json(args.spec)
    errors, _warnings = validate(spec)
    if errors:
        print("ERROR: invalid loop spec; fix these before running:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    def _shell(command, extra_env=None):
        return subprocess.run(
            command, shell=True, capture_output=True, text=True,
            env={**_os.environ, **(extra_env or {})},
        )

    def propose(context):
        completed = _shell(args.propose, {
            "SUPER_LOOPER_ITERATION": str(context["iteration"]),
            "SUPER_LOOPER_LAST_SIGNAL": context.get("last_signal") or "",
        })
        return completed.stdout.strip()

    def verify(_change):
        completed = _shell(args.verify)
        tail = [ln for ln in completed.stderr.strip().splitlines() if ln.strip()]
        signal = tail[-1] if tail else f"exit {completed.returncode}"
        return {"passed": completed.returncode == 0, "signal": signal}

    durable = (spec.get("state") or {}).get("durable_progress") or []
    state_path = args.state or (durable[0] if durable else "super-looper-state.json")
    result = run_loop(spec, propose=propose, verify=verify, store=FileStore(state_path))

    print(json.dumps({
        "reason": result.reason,
        "success": result.success,
        "iterations": result.iterations,
        "kept": result.kept,
        "state_file": state_path,
        "history": result.history,
    }, indent=2))
    return 0 if result.success else 1


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
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
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
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
    try:
        result = design_case_study(args.manifest)
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    report = result.get("report", {})
    return 1 if report.get("validation", {}).get("errors") else 0


def cmd_case_study_run(args):
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
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
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
    try:
        result = simulate_sketch_verifier(
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
    if args.strict and not summary.get("ready_for_sketch_report"):
        return 1
    return 0


def cmd_case_study_resolve_verifier(args):
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
    try:
        result = resolve_verifier(
            args.manifest,
            args.repo_path,
            template=args.template,
            sketch=not args.no_sketch,
            run_id=args.run_id,
        )
    except CaseStudyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    summary = result.get("summary", {})
    if args.strict:
        if summary.get("evidence_level") == "sketch":
            return 0 if summary.get("ready_for_sketch_report") else 1
        return 0 if summary.get("ready_for_pr_claim") else 1
    return 0


def cmd_case_study_verify(args):
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
    result = verify_run(args.run_dir)
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed") else 1


def cmd_case_study_report(args):
    from .experimental.case_study import CaseStudyError, create_manifest, design_case_study, render_report, resolve_verifier, run_case_study, simulate_sketch_verifier, verify_run, write_reports  # noqa: F401
    if args.print_report:
        print(render_report(args.run_dir, args.for_audience))
        return 0
    audience = "all" if args.for_audience == "all" else args.for_audience
    outputs = write_reports(args.run_dir, audience)
    print(json.dumps(outputs, indent=2))
    return 0


def cmd_runner_plan(args):
    from .experimental.remote_runner import RemoteRunnerError, build_bootstrap_plan, build_remote_runner_plan, create_runner_key  # noqa: F401
    try:
        profile = _load_json(args.profile) if args.profile else {}
        remote = args.remote or _profile_value(profile, "remote")
        identity_file = args.identity_file or _profile_value(profile, "identity_file")
        if not remote:
            raise RemoteRunnerError("--remote is required unless --profile supplies remote")
        if not identity_file:
            raise RemoteRunnerError("--identity-file is required unless --profile supplies identity_file")
        plan = build_remote_runner_plan(
            remote=remote,
            identity_file=identity_file,
            case_path=args.case,
            repo=args.repo,
            remote_workdir=args.remote_workdir or _profile_value(
                profile, "remote_workdir", "/tmp/super-looper-runs"
            ),
            run_id=args.run_id,
            setup=args.setup,
            isolation=args.isolation or _profile_value(profile, "isolation", "container"),
            allow_network_setup=args.allow_network_setup,
            allow_network_run=args.allow_network_run,
            accept_new_host_key=args.accept_new_host_key
            or bool(_profile_value(profile, "accept_new_host_key", False)),
            known_hosts=args.known_hosts or _profile_value(profile, "known_hosts"),
            allow_root=args.allow_root,
            keep_remote_workdir=args.keep_remote_workdir,
            container_engine=args.container_engine
            or _profile_value(profile, "container_engine", "podman"),
        )
    except RemoteRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.out:
        _write_json(args.out, plan)
    print(json.dumps(plan, indent=2))
    return 0


def cmd_runner_keygen(args):
    from .experimental.remote_runner import RemoteRunnerError, build_bootstrap_plan, build_remote_runner_plan, create_runner_key  # noqa: F401
    try:
        result = create_runner_key(
            name=args.name,
            out_dir=args.out_dir,
            force=args.force,
            comment=args.comment,
        )
    except RemoteRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.out:
        _write_json(args.out, result)
    print(json.dumps(result, indent=2))
    return 0


def cmd_runner_bootstrap_plan(args):
    from .experimental.remote_runner import RemoteRunnerError, build_bootstrap_plan, build_remote_runner_plan, create_runner_key  # noqa: F401
    try:
        plan = build_bootstrap_plan(
            provider=args.provider,
            ip=args.ip,
            admin_identity_file=args.admin_identity_file,
            runner_public_key_file=args.runner_public_key,
            runner_identity_file=args.runner_identity_file,
            name=args.name,
            admin_user=args.admin_user,
            runner_user=args.runner_user,
            remote_workdir=args.remote_workdir,
            container_engine=args.container_engine,
            accept_new_host_key=args.accept_new_host_key,
            known_hosts=args.known_hosts,
        )
    except RemoteRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.profile_out:
        _write_json(args.profile_out, plan["runner_profile"])
    if args.out:
        _write_json(args.out, plan)
    print(json.dumps(plan, indent=2))
    return 0


def cmd_repo_audit(args):
    from .repo_audit import RepoAuditError, audit_repo, promote_candidate, write_audit_outputs  # noqa: F401
    try:
        result = audit_repo(args.repo_path, max_files=args.max_files)
        outputs = write_audit_outputs(result, args.out) if args.out else {}
    except RepoAuditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        payload = dict(result)
        if outputs:
            payload["outputs"] = outputs
        print(json.dumps(payload, indent=2))
    else:
        summary = result["summary"]
        print("repo audit complete")
        print(f"repo: {result['repo']['path']}")
        print(
            "gates: "
            f"{summary['gate_counts']['strong']} strong, "
            f"{summary['gate_counts']['medium']} medium, "
            f"{summary['gate_counts']['weak']} weak"
        )
        print("candidates:")
        for candidate in [item for item in result["automation_candidates"] if not item.get("hypothesis")][:8]:
            print(
                f"- {candidate['title']} "
                f"[{candidate['recommended_path']}, max={candidate['max_agent_autonomy']}, "
                f"gate={candidate['gate_strength']}, score={candidate['score']['total']}]"
            )
        hypotheses = [item for item in result["automation_candidates"] if item.get("hypothesis")]
        if hypotheses:
            print("hypotheses:")
            for candidate in hypotheses[:5]:
                print(
                    f"- {candidate['title']} "
                    f"[{candidate['recommended_path']}, max={candidate['max_agent_autonomy']}, "
                    f"score={candidate['score']['total']}]"
                )
        if outputs:
            print("outputs:")
            for key, path in outputs.items():
                print(f"- {key}: {path}")
    return 0


def cmd_repo_promote(args):
    from .repo_audit import RepoAuditError, audit_repo, promote_candidate, write_audit_outputs  # noqa: F401
    try:
        result = promote_candidate(
            audit_path=args.audit,
            candidate_id=args.candidate,
            out_dir=args.out,
            repo=args.repo,
            issue=args.issue,
            name=args.name,
            max_runtime_seconds=args.max_runtime_seconds,
            out_root=args.out_root,
            answers_path=args.answers,
        )
    except RepoAuditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
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

    run_cmd = sub.add_parser("run", help="drive a validated loop's deterministic skeleton (you supply the model and gate commands)")
    run_cmd.add_argument("spec", help="path to a loop spec JSON")
    run_cmd.add_argument("--propose", required=True, help="shell command for the model's propose step (gets SUPER_LOOPER_ITERATION / SUPER_LOOPER_LAST_SIGNAL in env)")
    run_cmd.add_argument("--verify", required=True, help="shell command for the gate; exit 0 = pass")
    run_cmd.add_argument("--state", help="durable state JSON file (default: spec.state.durable_progress[0])")
    run_cmd.set_defaults(func=cmd_run)

    repo = sub.add_parser("repo", help="discover repo-native gates and automation candidates")
    repo_sub = repo.add_subparsers(dest="repo_command", required=True)

    repo_audit = repo_sub.add_parser("audit", help="rank conservative automation candidates for a local repository")
    repo_audit.add_argument("--repo-path", required=True, help="local repository checkout to audit")
    repo_audit.add_argument("--out", help="directory for repo-audit.json, gate inventory, surfaces, loop hypotheses, backlog, and recommendations")
    repo_audit.add_argument("--max-files", type=int, default=50000, help="maximum repository files to index")
    repo_audit.add_argument("--json", action="store_true", help="print full JSON audit")
    repo_audit.set_defaults(func=cmd_repo_audit)

    repo_promote = repo_sub.add_parser(
        "promote",
        help="promote one audit candidate into a clean case-study proof packet",
    )
    repo_promote.add_argument("--audit", required=True, help="repo-audit.json written by repo audit")
    repo_promote.add_argument("--candidate", required=True, help="candidate id from repo-audit.json")
    repo_promote.add_argument("--out", help="exact directory for the promoted proof packet")
    repo_promote.add_argument(
        "--out-root",
        default="case-studies",
        help="root used when --out is omitted; writes <root>/<repo-slug>/<candidate-slug>",
    )
    repo_promote.add_argument("--repo", help="repository URL or owner/name to store in the case-study manifest")
    repo_promote.add_argument("--issue", help="optional issue URL or identifier")
    repo_promote.add_argument("--name", help="case-study manifest name")
    repo_promote.add_argument("--max-runtime-seconds", type=int, default=1800, help="runtime budget for verifier runs")
    repo_promote.add_argument("--answers", help="JSON of human answers to supplement the lead (fills gaps a static scan can't know, so a borderline lead can qualify)")
    repo_promote.set_defaults(func=cmd_repo_promote)

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

    case_sketch = case_sub.add_parser("sketch-verifier", aliases=["simulate-verifier"], help="generate and run a verifier SKETCH without modifying the checkout (proposal only, never proof)")
    case_sketch.add_argument("manifest", help="case-study manifest path or directory")
    case_sketch.add_argument("--repo-path", required=True, help="local checkout of the target repository")
    case_sketch.add_argument("--template", default="python-ast-corpus", choices=["python-ast-corpus"], help="verifier sketch template")
    case_sketch.add_argument("--run-id", help="stable run directory name; defaults to UTC timestamp")
    case_sketch.add_argument("--strict", action="store_true", help="exit nonzero unless the verifier sketch and scope both pass")
    case_sketch.set_defaults(func=cmd_case_study_simulate_verifier)

    case_resolve = case_sub.add_parser("resolve-verifier", help="run the confirmed verifier or fall back to a verifier sketch by default")
    case_resolve.add_argument("manifest", help="case-study manifest path or directory")
    case_resolve.add_argument("--repo-path", required=True, help="local checkout of the target repository")
    case_resolve.add_argument("--template", default="python-ast-corpus", choices=["python-ast-corpus"], help="verifier sketch template when fallback is needed")
    case_resolve.add_argument("--run-id", help="stable run directory name; defaults to UTC timestamp")
    case_resolve.add_argument("--no-sketch", "--no-shadow", action="store_true", help="do not generate a verifier sketch when the declared gate is missing")
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

    runner = sub.add_parser("runner", help="plan isolated case-study execution on remote runners")
    runner_sub = runner.add_subparsers(dest="runner_command", required=True)

    runner_keygen = runner_sub.add_parser("keygen", help="create a dedicated runner SSH keypair")
    runner_keygen.add_argument("--name", required=True, help="runner/profile name")
    runner_keygen.add_argument("--out-dir", default=".super-looper/runners", help="directory for the keypair")
    runner_keygen.add_argument("--comment", help="SSH public-key comment")
    runner_keygen.add_argument("--force", action="store_true", help="replace an existing runner keypair")
    runner_keygen.add_argument("--out", help="write the JSON key metadata to this path")
    runner_keygen.set_defaults(func=cmd_runner_keygen)

    runner_bootstrap = runner_sub.add_parser(
        "bootstrap-plan",
        help="write a provider-aware bootstrap plan for a fresh disposable Linux VM",
    )
    runner_bootstrap.add_argument(
        "--provider",
        choices=["digitalocean", "aws", "gcp", "azure", "hetzner", "custom"],
        default="digitalocean",
        help="VM provider preset; execution remains generic SSH",
    )
    runner_bootstrap.add_argument("--ip", required=True, help="VM IP address or DNS name")
    runner_bootstrap.add_argument(
        "--admin-identity-file",
        required=True,
        help="temporary admin SSH private key for bootstrapping the VM",
    )
    runner_bootstrap.add_argument(
        "--runner-public-key",
        required=True,
        help="public key to install for the non-root runner user",
    )
    runner_bootstrap.add_argument(
        "--runner-identity-file",
        required=True,
        help="matching runner private key path to store in the reusable profile",
    )
    runner_bootstrap.add_argument("--name", default="sandbox1", help="runner/profile name")
    runner_bootstrap.add_argument("--admin-user", default="root", help="admin bootstrap user")
    runner_bootstrap.add_argument("--runner-user", default="runner", help="non-root runner account to create")
    runner_bootstrap.add_argument("--remote-workdir", default="/tmp/super-looper-runs", help="dedicated remote parent directory")
    runner_bootstrap.add_argument("--container-engine", choices=["podman", "docker"], default="podman", help="container engine to install/use")
    runner_bootstrap.add_argument("--accept-new-host-key", action="store_true", help="use StrictHostKeyChecking=accept-new instead of requiring a pinned host key")
    runner_bootstrap.add_argument("--known-hosts", help="known_hosts file to pin the VM host key")
    runner_bootstrap.add_argument("--profile-out", help="write the reusable runner profile JSON here")
    runner_bootstrap.add_argument("--out", help="write the full bootstrap plan JSON here")
    runner_bootstrap.set_defaults(func=cmd_runner_bootstrap_plan)

    runner_plan = runner_sub.add_parser("plan", help="write a hardened remote-VM execution plan without running SSH")
    runner_plan.add_argument("--profile", help="runner profile JSON from runner bootstrap-plan --profile-out")
    runner_plan.add_argument("--remote", help="ssh://user@host[:port] or user@host[:port]")
    runner_plan.add_argument("--identity-file", help="dedicated SSH private key for the runner VM")
    runner_plan.add_argument("--case", required=True, help="case-study manifest path or directory to bundle")
    runner_plan.add_argument("--repo", help="public repo URL to clone inside the VM")
    runner_plan.add_argument("--remote-workdir", help="dedicated remote parent directory")
    runner_plan.add_argument("--run-id", help="stable run id for the remote workdir")
    runner_plan.add_argument("--setup", choices=["none", "deps"], default="none", help="dependency setup mode")
    runner_plan.add_argument("--isolation", choices=["container", "remote-vm"], help="remote execution isolation tier")
    runner_plan.add_argument("--container-engine", choices=["podman", "docker"], help="container engine used on the remote VM")
    runner_plan.add_argument("--allow-network-setup", action="store_true", help="allow network only during explicit dependency setup")
    runner_plan.add_argument("--allow-network-run", action="store_true", help="allow network during verifier execution")
    runner_plan.add_argument("--accept-new-host-key", action="store_true", help="use StrictHostKeyChecking=accept-new instead of requiring a pinned host key")
    runner_plan.add_argument("--known-hosts", help="known_hosts file to pin the VM host key")
    runner_plan.add_argument("--allow-root", action="store_true", help="permit root SSH user for disposable VMs")
    runner_plan.add_argument("--keep-remote-workdir", action="store_true", help="do not delete the remote run directory in the cleanup plan")
    runner_plan.add_argument("--out", help="write the JSON plan to this path")
    runner_plan.set_defaults(func=cmd_runner_plan)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
