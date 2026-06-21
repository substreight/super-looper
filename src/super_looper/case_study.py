"""Case-study harness for running loop designs against real repositories."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .design import build_spec
from .validate import max_autonomy, render_plain, validate


DEFAULT_MANIFEST = "case-study.json"


class CaseStudyError(RuntimeError):
    """Raised when a case-study command cannot proceed."""


def _utc_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")


def _json_load(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise CaseStudyError(f"{path} must contain a JSON object")
    return data


def _json_write(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def _text_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        if text and not text.endswith("\n"):
            f.write("\n")


def _slug(text: str) -> str:
    bits = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(bits[:8]) or "case-study"


def _split_items(values: Optional[Sequence[str]]) -> List[str]:
    out: List[str] = []
    for value in values or []:
        for part in str(value).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _resolve_manifest(path: str) -> Tuple[str, str, Dict[str, Any]]:
    manifest_path = os.path.abspath(path)
    if os.path.isdir(manifest_path):
        manifest_path = os.path.join(manifest_path, DEFAULT_MANIFEST)
    manifest = _json_load(manifest_path)
    return manifest_path, os.path.dirname(manifest_path), manifest


def _resolve_relative(base_dir: str, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def _rel(base_dir: str, path: str) -> str:
    return os.path.relpath(path, base_dir).replace("\\", "/")


def create_manifest(
    out_dir: str,
    repo: str,
    issue: Optional[str] = None,
    name: Optional[str] = None,
    answers: Optional[str] = None,
    verifier: Optional[Sequence[str]] = None,
    may_touch: Optional[Sequence[str]] = None,
    must_not_touch: Optional[Sequence[str]] = None,
    max_runtime_seconds: int = 1800,
) -> Dict[str, Any]:
    """Create a case-study directory with a manifest and optional answers copy."""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    study_name = name or _slug(os.path.splitext(os.path.basename(out_dir.rstrip(os.sep)))[0] or repo)
    answers_name = "answers.json"
    if answers:
        shutil.copyfile(os.path.abspath(answers), os.path.join(out_dir, answers_name))
    else:
        _json_write(os.path.join(out_dir, answers_name), {
            "task": "",
            "recurs": "unknown",
            "wrong_result_signal": "unknown",
            "finished_state": "unknown",
            "may_touch": [],
            "must_not_touch": [],
            "budget": {"max_runtime_seconds": max_runtime_seconds},
        })

    manifest = {
        "name": study_name,
        "repo": repo,
        "issue": issue or "",
        "answers": answers_name,
        "loop_spec": "loop.json",
        "verifier": list(verifier or []),
        "may_touch": _split_items(may_touch),
        "must_not_touch": _split_items(must_not_touch),
        "budget": {"max_runtime_seconds": max_runtime_seconds},
        "runs_dir": "runs",
    }
    manifest_path = os.path.join(out_dir, DEFAULT_MANIFEST)
    _json_write(manifest_path, manifest)
    return {"manifest_path": manifest_path, "manifest": manifest}


def design_case_study(manifest_path: str) -> Dict[str, Any]:
    """Compile the manifest's answers into a loop spec and design report."""
    manifest_path, base_dir, manifest = _resolve_manifest(manifest_path)
    answers_path = _resolve_relative(base_dir, manifest.get("answers"))
    if answers_path is None:
        raise CaseStudyError("manifest missing answers path")
    answers = _json_load(answers_path)

    spec, report = build_spec(answers)
    result = {
        "manifest": _rel(base_dir, manifest_path),
        "answers": _rel(base_dir, answers_path),
        "report": report,
    }
    if spec is not None:
        loop_path = _resolve_relative(base_dir, manifest.get("loop_spec") or "loop.json")
        assert loop_path is not None
        _json_write(loop_path, spec)
        result["loop_spec"] = _rel(base_dir, loop_path)
        result["max_autonomy"] = max_autonomy(spec)[0]
    _json_write(os.path.join(base_dir, "design-report.json"), result)
    return result


def _run_command(
    command: str,
    cwd: str,
    timeout_seconds: int,
    stdout_path: Optional[str] = None,
    stderr_path: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.monotonic()
    timed_out = False
    exit_code: Optional[int] = None
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = _decode_timeout_output(exc.stdout)
        stderr = _decode_timeout_output(exc.stderr)
    duration = round(time.monotonic() - started, 3)

    if stdout_path:
        _text_write(stdout_path, stdout)
    if stderr_path:
        _text_write(stderr_path, stderr)

    return {
        "command": command,
        "cwd": cwd,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "stdout_path": os.path.basename(stdout_path) if stdout_path else None,
        "stderr_path": os.path.basename(stderr_path) if stderr_path else None,
    }


def _decode_timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _git(repo_path: str, args: Sequence[str], timeout_seconds: int = 30) -> Dict[str, Any]:
    command = ["git"] + list(args)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def probe_repo(repo_path: str) -> Dict[str, Any]:
    """Collect repository metadata without requiring network access."""
    repo_path = os.path.abspath(repo_path)
    markers = [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "Makefile",
        ".github/workflows",
    ]
    return {
        "path": repo_path,
        "head": _git(repo_path, ["rev-parse", "HEAD"]),
        "branch": _git(repo_path, ["branch", "--show-current"]),
        "remote": _git(repo_path, ["remote", "get-url", "origin"]),
        "status_short": _git(repo_path, ["status", "--short"]),
        "detected": [marker for marker in markers if os.path.exists(os.path.join(repo_path, marker))],
    }


def _changed_files(repo_path: str) -> List[str]:
    files = []
    for args in (["diff", "--name-only"], ["ls-files", "--others", "--exclude-standard"]):
        result = _git(repo_path, args)
        if not result.get("ok"):
            continue
        files.extend(line.strip().replace("\\", "/")
                     for line in result.get("stdout", "").splitlines()
                     if line.strip())
    return sorted(set(files))


def _write_diff(repo_path: str, run_dir: str) -> Dict[str, Any]:
    result = _git(repo_path, ["diff", "--no-ext-diff"], timeout_seconds=60)
    patch_path = os.path.join(run_dir, "diff.patch")
    _text_write(patch_path, result.get("stdout", ""))
    return {
        "path": "diff.patch",
        "exit_code": result.get("exit_code"),
        "ok": result.get("ok"),
        "stderr": result.get("stderr"),
    }


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _matches_rule(path: str, rule: str) -> bool:
    path = _norm_path(path)
    rule = _norm_path(rule)
    if not rule:
        return False
    if rule.endswith("/"):
        return path.startswith(rule)
    return path == rule or path.startswith(rule + "/")


def check_scope(changed_files: Iterable[str], may_touch: Sequence[str], must_not_touch: Sequence[str]) -> Dict[str, Any]:
    """Check changed files against may-touch and must-not-touch fences."""
    files = [_norm_path(f) for f in changed_files if str(f).strip()]
    outside = []
    forbidden = []
    for path in files:
        if any(_matches_rule(path, rule) for rule in must_not_touch):
            forbidden.append(path)
        if may_touch and not any(_matches_rule(path, rule) for rule in may_touch):
            outside.append(path)
        elif not may_touch:
            outside.append(path)
    return {
        "passed": not outside and not forbidden,
        "changed_files": files,
        "outside_may_touch": outside,
        "inside_must_not_touch": forbidden,
    }


def _budget_seconds(manifest: Dict[str, Any], spec: Optional[Dict[str, Any]]) -> int:
    for budget in (
        manifest.get("budget"),
        (spec or {}).get("stop_conditions", {}).get("budget") if isinstance(spec, dict) else None,
    ):
        if isinstance(budget, dict):
            val = budget.get("max_runtime_seconds")
            if isinstance(val, int) and val > 0:
                return val
    return 1800


def _load_loop_spec(base_dir: str, manifest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    path = _resolve_relative(base_dir, manifest.get("loop_spec"))
    if path and os.path.exists(path):
        return _json_load(path)
    return None


def run_case_study(
    manifest_path: str,
    repo_path: str,
    run_id: Optional[str] = None,
    skip_verifier: bool = False,
) -> Dict[str, Any]:
    """Run a case study against an already-cloned repository."""
    manifest_path, base_dir, manifest = _resolve_manifest(manifest_path)
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        raise CaseStudyError(f"repo path does not exist: {repo_path}")

    loop_spec = _load_loop_spec(base_dir, manifest)
    run_root = _resolve_relative(base_dir, manifest.get("runs_dir") or "runs")
    assert run_root is not None
    run_dir = os.path.join(run_root, run_id or _utc_id())
    os.makedirs(run_dir, exist_ok=True)

    _json_write(os.path.join(run_dir, "manifest.json"), manifest)
    if loop_spec is not None:
        _json_write(os.path.join(run_dir, "loop.json"), loop_spec)
        level, missing = max_autonomy(loop_spec)
        _json_write(os.path.join(run_dir, "autonomy.json"), {
            "max_autonomy": level,
            "missing_for_more_autonomy": missing,
        })

    repo_meta = probe_repo(repo_path)
    _json_write(os.path.join(run_dir, "repo.json"), repo_meta)
    _json_write(os.path.join(run_dir, "issue.json"), {
        "source": manifest.get("issue") or "",
        "note": "Network lookup is intentionally out of scope for local runs; attach fetched issue context separately if needed.",
    })

    commands = list(manifest.get("verifier") or [])
    timeout_seconds = _budget_seconds(manifest, loop_spec)
    command_results = []
    deadline = time.monotonic() + timeout_seconds
    if not skip_verifier:
        for idx, command in enumerate(commands, start=1):
            remaining_raw = deadline - time.monotonic()
            if remaining_raw <= 0:
                command_results.append({
                    "command": command,
                    "cwd": repo_path,
                    "exit_code": None,
                    "timed_out": True,
                    "duration_seconds": 0,
                    "stdout_path": None,
                    "stderr_path": None,
                })
                continue
            remaining = max(1, int(remaining_raw))
            command_results.append(_run_command(
                command,
                repo_path,
                remaining,
                os.path.join(run_dir, f"command-{idx}.stdout.txt"),
                os.path.join(run_dir, f"command-{idx}.stderr.txt"),
            ))
    verifier_results = {
        "skipped": bool(skip_verifier),
        "declared_commands": commands,
        "commands": command_results,
        "passed": (not skip_verifier) and bool(commands) and all(
            r.get("exit_code") == 0 and not r.get("timed_out") for r in command_results
        ),
    }
    _json_write(os.path.join(run_dir, "verifier-results.json"), verifier_results)

    changed = _changed_files(repo_path)
    scope = check_scope(
        changed,
        manifest.get("may_touch") or (loop_spec or {}).get("scope", {}).get("may_touch", []),
        manifest.get("must_not_touch") or (loop_spec or {}).get("scope", {}).get("must_not_touch", []),
    )
    _json_write(os.path.join(run_dir, "scope-check.json"), scope)
    diff_meta = _write_diff(repo_path, run_dir)
    _json_write(os.path.join(run_dir, "diff.json"), diff_meta)

    summary = summarize_run(run_dir)
    _json_write(os.path.join(run_dir, "summary.json"), summary)
    write_reports(run_dir)
    return {"run_dir": run_dir, "summary": summary}


def _load_optional_json(path: str) -> Dict[str, Any]:
    return _json_load(path) if os.path.exists(path) else {}


def summarize_run(run_dir: str) -> Dict[str, Any]:
    """Summarize a completed or partially completed run directory."""
    run_dir = os.path.abspath(run_dir)
    manifest = _load_optional_json(os.path.join(run_dir, "manifest.json"))
    verifier = _load_optional_json(os.path.join(run_dir, "verifier-results.json"))
    scope = _load_optional_json(os.path.join(run_dir, "scope-check.json"))
    autonomy = _load_optional_json(os.path.join(run_dir, "autonomy.json"))
    repo = _load_optional_json(os.path.join(run_dir, "repo.json"))
    loop = _load_optional_json(os.path.join(run_dir, "loop.json"))
    errors, warnings = validate(loop) if loop else (["loop.json missing"], [])
    return {
        "name": manifest.get("name") or os.path.basename(os.path.dirname(run_dir)),
        "repo": manifest.get("repo") or repo.get("remote", {}).get("stdout", ""),
        "issue": manifest.get("issue", ""),
        "verifier_passed": verifier.get("passed") is True,
        "verifier_skipped": verifier.get("skipped") is True,
        "scope_passed": scope.get("passed") is True,
        "changed_files": scope.get("changed_files", []),
        "max_autonomy": autonomy.get("max_autonomy"),
        "missing_for_more_autonomy": autonomy.get("missing_for_more_autonomy", []),
        "loop_valid": not errors,
        "loop_errors": errors,
        "loop_warnings": warnings,
        "ready_for_pr_claim": verifier.get("passed") is True and scope.get("passed") is True and not errors,
    }


def verify_run(run_dir: str) -> Dict[str, Any]:
    """Return summary plus a process-friendly pass/fail flag."""
    summary = summarize_run(run_dir)
    failures = []
    if not summary["loop_valid"]:
        failures.append("loop spec is invalid")
    if summary["verifier_skipped"]:
        failures.append("verifier was skipped")
    elif not summary["verifier_passed"]:
        failures.append("verifier did not pass")
    if not summary["scope_passed"]:
        failures.append("scope check did not pass")
    return {"passed": not failures, "failures": failures, "summary": summary}


def _commands_table(verifier: Dict[str, Any]) -> str:
    commands = verifier.get("commands") or []
    if verifier.get("skipped"):
        declared = verifier.get("declared_commands") or []
        if declared:
            return "\n".join(f"- `{command}` -> skipped" for command in declared)
        return "- Verifier was skipped and no commands were declared."
    if not commands:
        return "- No verifier commands were recorded."
    lines = []
    for item in commands:
        status = "pass" if item.get("exit_code") == 0 and not item.get("timed_out") else "fail"
        if item.get("timed_out"):
            status = "timeout"
        lines.append(
            f"- `{item.get('command')}` -> {status} "
            f"(exit={item.get('exit_code')}, {item.get('duration_seconds')}s)"
        )
    return "\n".join(lines)


def render_report(run_dir: str, audience: str = "maintainer") -> str:
    """Render a maintainer-facing or PR-facing markdown report."""
    run_dir = os.path.abspath(run_dir)
    summary = summarize_run(run_dir)
    manifest = _load_optional_json(os.path.join(run_dir, "manifest.json"))
    verifier = _load_optional_json(os.path.join(run_dir, "verifier-results.json"))
    scope = _load_optional_json(os.path.join(run_dir, "scope-check.json"))
    loop = _load_optional_json(os.path.join(run_dir, "loop.json"))

    title = summary.get("name") or "case study"
    if audience == "pr":
        heading = "## Summary"
        purpose = "This PR packages a Super Looper case-study run with reproducible verifier and scope evidence."
    else:
        heading = f"# Super Looper Report: {title}"
        purpose = "This is a quick reproducible report from a guarded Super Looper case-study run."

    lines = [heading, "", purpose, ""]
    if audience != "pr":
        lines.extend([
            f"- Repo: {summary.get('repo') or manifest.get('repo') or 'unknown'}",
            f"- Issue: {summary.get('issue') or 'not provided'}",
            f"- Max earned autonomy: {summary.get('max_autonomy') or 'unknown'}",
            f"- PR-ready claim: {'yes' if summary.get('ready_for_pr_claim') else 'no'}",
            "",
        ])
    else:
        lines.extend([
            f"- Target issue: {summary.get('issue') or 'not provided'}",
            f"- Max earned autonomy: {summary.get('max_autonomy') or 'unknown'}",
            f"- Scope check: {'passed' if summary.get('scope_passed') else 'failed'}",
            f"- Verifier: {'passed' if summary.get('verifier_passed') else 'not passed'}",
            "",
        ])

    if loop:
        try:
            lines.extend(["## Loop Preview", "", render_plain(loop), ""])
        except Exception:
            pass

    lines.extend([
        "## Verification",
        "",
        _commands_table(verifier),
        "",
        "## Scope Guard",
        "",
        f"- Passed: {'yes' if scope.get('passed') else 'no'}",
        f"- Changed files: {len(scope.get('changed_files') or [])}",
    ])
    for path in scope.get("changed_files") or []:
        lines.append(f"  - `{path}`")
    if scope.get("outside_may_touch"):
        lines.append("- Outside may_touch:")
        for path in scope["outside_may_touch"]:
            lines.append(f"  - `{path}`")
    if scope.get("inside_must_not_touch"):
        lines.append("- Inside must_not_touch:")
        for path in scope["inside_must_not_touch"]:
            lines.append(f"  - `{path}`")

    lines.extend(["", "## Artifacts", "", "- `summary.json`", "- `verifier-results.json`", "- `scope-check.json`", "- `diff.patch`"])
    if summary.get("missing_for_more_autonomy"):
        lines.extend(["", "## Missing For More Autonomy", ""])
        for item in summary["missing_for_more_autonomy"]:
            lines.append(f"- {item}")

    if not summary.get("ready_for_pr_claim"):
        lines.extend([
            "",
            "## Status",
            "",
            "Do not claim this as shipped until the verifier passes and the scope guard is clean.",
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_reports(run_dir: str, audience: str = "all") -> Dict[str, str]:
    """Write report markdown files for the requested audience."""
    outputs = {}
    if audience in ("maintainer", "all"):
        path = os.path.join(run_dir, "report-maintainer.md")
        _text_write(path, render_report(run_dir, "maintainer"))
        outputs["maintainer"] = path
    if audience in ("pr", "all"):
        path = os.path.join(run_dir, "report-pr.md")
        _text_write(path, render_report(run_dir, "pr"))
        outputs["pr"] = path
    return outputs
