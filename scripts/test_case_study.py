#!/usr/bin/env python3
"""Tests for the case-study harness. Runs under pytest or standalone."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.case_study import (  # noqa: E402
    check_scope,
    create_manifest,
    design_case_study,
    run_case_study,
    simulate_shadow_verifier,
    verify_run,
)


ANSWERS = {
    "task": "Track invalid syntax in generated Python compression output",
    "recurs": True,
    "wrong_result_signal": "pytest exits nonzero OR invalid_syntax_count > 0",
    "gate_check": "pytest exits 0 AND invalid_syntax_count == 0",
    "finished_state": "generated Python compression output parses successfully",
    "evidence": "python -m pytest tests/test_compression_corpus.py exits 0",
    "may_touch": ["src/compressor.py", "tests/"],
    "must_not_touch": ["pyproject.toml", "secrets/"],
    "budget": {"max_runtime_seconds": 60},
    "budget_summary": "at most 60 seconds",
    "unattended": False,
    "output_reversibility": "reversible",
    "gate_rung": "tool",
    "end_to_end": True,
}


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _fake_headroom_repo(root):
    _write_text(os.path.join(root, "headroom", "__init__.py"), "")
    _write_text(os.path.join(root, "headroom", "transforms", "__init__.py"), "")
    _write_text(os.path.join(root, "headroom", "transforms", "code_compressor.py"), """
from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class CodeCompressorConfig:
    min_tokens_for_compression: int = 1
    max_body_lines: int = 2
    enable_ccr: bool = False
    semantic_analysis: bool = False
    fallback_to_kompress: bool = False
    language_hint: str = "python"


class CodeAwareCompressor:
    def __init__(self, config=None):
        self.config = config or CodeCompressorConfig()

    def compress(self, source, language=None):
        return SimpleNamespace(compressed=source, compressed_bodies=1, syntax_valid=True)
""")
    _write_text(os.path.join(root, "headroom", "sample.py"), """
def alpha(value: int) -> int:
    total = value
    for item in range(5):
        total += item
    return total


class Beta:
    def run(self) -> str:
        return "ok"
""")


def test_scope_guard_accepts_allowed_paths():
    result = check_scope(
        ["src/compressor.py", "tests/test_compression.py"],
        ["src/", "tests/"],
        ["secrets/", "pyproject.toml"],
    )
    assert result["passed"], result


def test_scope_guard_rejects_outside_and_forbidden_paths():
    result = check_scope(
        ["src/compressor.py", "docs/report.md", "secrets/token.txt"],
        ["src/"],
        ["secrets/"],
    )
    assert not result["passed"], result
    assert "docs/report.md" in result["outside_may_touch"], result
    assert "secrets/token.txt" in result["inside_must_not_touch"], result


def test_case_study_design_run_verify_and_report():
    with tempfile.TemporaryDirectory() as root:
        case_dir = os.path.join(root, "compression-case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            issue="https://example.test/repo/issues/1",
            verifier=[f'"{sys.executable}" -c "print(\'ok\')"'],
            may_touch=["src/", "tests/"],
            must_not_touch=["secrets/", "pyproject.toml"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        design = design_case_study(created["manifest_path"])
        assert design["report"]["verdict"] == "AUTONOMOUS_LOOP", design
        assert design["report"]["validation"]["errors"] == [], design

        run = run_case_study(created["manifest_path"], root, run_id="run-1")
        assert run["summary"]["verifier_passed"], run
        assert run["summary"]["scope_passed"], run

        verified = verify_run(run["run_dir"])
        assert verified["passed"], verified
        assert os.path.exists(os.path.join(run["run_dir"], "report-maintainer.md"))
        assert os.path.exists(os.path.join(run["run_dir"], "report-pr.md"))


def test_case_study_scope_guard_sees_untracked_files():
    if shutil.which("git") is None:
        return
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(os.path.join(repo, "docs"))
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        with open(os.path.join(repo, "docs", "report.md"), "w", encoding="utf-8") as f:
            f.write("untracked report\n")

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=[f'"{sys.executable}" -c "print(\'ok\')"'],
            may_touch=["src/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)
        design_case_study(created["manifest_path"])

        run = run_case_study(created["manifest_path"], repo, run_id="run-1")
        assert not run["summary"]["scope_passed"], run
        assert "docs/report.md" in run["summary"]["changed_files"], run


def test_shadow_verifier_runs_without_modifying_checkout():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _fake_headroom_repo(repo)

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            may_touch=["tests/test_transforms/"],
            must_not_touch=["pyproject.toml"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = simulate_shadow_verifier(created["manifest_path"], repo, run_id="shadow-1")
        assert run["summary"]["evidence_level"] == "shadow", run
        assert run["summary"]["ready_for_shadow_report"], run
        assert not run["summary"]["ready_for_pr_claim"], run
        assert os.path.exists(os.path.join(run["run_dir"], "shadow.patch"))
        assert os.path.exists(os.path.join(run["run_dir"], "shadow-proposed", "tests", "test_transforms", "test_code_compressor_corpus.py"))
        assert not os.path.exists(os.path.join(repo, "tests", "test_transforms", "test_code_compressor_corpus.py"))


def test_shadow_verifier_respects_scope_before_running():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _fake_headroom_repo(repo)

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            may_touch=["src/"],
            must_not_touch=["pyproject.toml"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = simulate_shadow_verifier(created["manifest_path"], repo, run_id="shadow-1")
        assert not run["summary"]["scope_passed"], run
        assert not run["summary"]["ready_for_shadow_report"], run
        assert run["shadow_verifier"]["status"] == "shadow_failed", run


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
