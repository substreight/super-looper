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

from super_looper.experimental.case_study import (  # noqa: E402
    CaseStudyError,
    _json_load,
    _json_write,
    check_scope,
    create_manifest,
    design_case_study,
    resolve_verifier,
    run_case_study,
    simulate_sketch_verifier,
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
        return SimpleNamespace(compressed=source + "\\n# compressed", compression_ratio=0.9, syntax_valid=True)
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


def test_corrupt_json_file_raises_clean_case_study_error():
    # Crash-corrupted evidence must surface as a clean CaseStudyError, never a raw
    # json.JSONDecodeError traceback, so a harness can gate on it.
    with tempfile.TemporaryDirectory() as root:
        bad = os.path.join(root, "corrupt.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{this is not valid json")
        raised = None
        try:
            _json_load(bad)
        except Exception as exc:
            raised = exc
        assert isinstance(raised, CaseStudyError), f"expected CaseStudyError, got {type(raised).__name__}"


def test_json_write_is_atomic_no_tmp_left_behind():
    # _json_write writes via a temp file + atomic os.replace: after success the
    # file holds exactly the payload and no .tmp sibling remains.
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "nested", "out.json")
        payload = {"evidence_level": "confirmed_local", "n": 7}
        _json_write(path, payload)
        with open(path, encoding="utf-8") as f:
            assert json.load(f) == payload
        leftover = [p for p in os.listdir(os.path.dirname(path)) if p.endswith(".tmp")]
        assert leftover == [], leftover


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


def test_direct_run_with_pathless_verifier_is_unconfirmed_not_pr_ready():
    # A passing verifier with no file-path token (e.g. `echo ok`) cannot be
    # statically confirmed as a real gate, so a DIRECT `case-study run` must
    # label it 'unconfirmed' (never confirmed_local / ready_for_pr_claim) --
    # matching resolve_verifier's no-path-token branch. Without this, the direct
    # run path silently bypasses the evidence-as-proof fence.
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=["echo ok"],
            may_touch=["src/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)
        design_case_study(created["manifest_path"])

        run = run_case_study(created["manifest_path"], repo, run_id="run-1")
        assert run["summary"]["evidence_level"] == "unconfirmed", run["summary"]
        assert run["summary"]["ready_for_pr_claim"] is False, run["summary"]


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


def test_sketch_verifier_runs_without_modifying_checkout():
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

        run = simulate_sketch_verifier(created["manifest_path"], repo, run_id="sketch-1")
        assert run["summary"]["evidence_level"] == "sketch", run
        assert run["summary"]["ready_for_sketch_report"], run
        assert not run["summary"]["ready_for_pr_claim"], run
        assert os.path.exists(os.path.join(run["run_dir"], "sketch.patch"))
        assert os.path.exists(os.path.join(run["run_dir"], "sketch-proposed", "tests", "test_transforms", "test_code_compressor_corpus.py"))
        assert not os.path.exists(os.path.join(repo, "tests", "test_transforms", "test_code_compressor_corpus.py"))


def test_sketch_verifier_respects_scope_before_running():
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

        run = simulate_sketch_verifier(created["manifest_path"], repo, run_id="sketch-1")
        assert not run["summary"]["scope_passed"], run
        assert not run["summary"]["ready_for_sketch_report"], run
        assert run["sketch_verifier"]["status"] == "sketch_failed", run


def test_resolve_verifier_runs_confirmed_gate_when_path_exists():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        _write_text(os.path.join(repo, "tests", "test_ok.py"), "def test_ok():\n    assert True\n")

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=[f'"{sys.executable}" -m pytest tests/test_ok.py'],
            may_touch=["tests/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = resolve_verifier(created["manifest_path"], repo, run_id="resolve-1")
        assert run["summary"]["evidence_level"] == "confirmed_local", run
        assert run["summary"]["claim_allowed"] == "local_verification", run
        assert run["summary"]["ready_for_pr_claim"], run
        assert run["verifier_resolution"]["status"] == "confirmed_gate_found", run


def test_resolve_verifier_defaults_to_sketch_when_declared_path_missing():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _fake_headroom_repo(repo)

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=[f'"{sys.executable}" -m pytest tests/test_missing_corpus.py'],
            may_touch=["tests/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = resolve_verifier(created["manifest_path"], repo, run_id="resolve-1")
        assert run["summary"]["evidence_level"] == "sketch", run
        assert run["summary"]["claim_allowed"] == "proposal_only", run
        assert not run["summary"]["ready_for_pr_claim"], run
        assert run["verifier_resolution"]["sketch_enabled"] is True, run
        assert run["verifier_resolution"]["missing_paths"] == ["tests/test_missing_corpus.py"], run


def test_resolve_verifier_no_sketch_reports_missing_gate():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=[f'"{sys.executable}" -m pytest tests/test_missing_corpus.py'],
            may_touch=["tests/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = resolve_verifier(created["manifest_path"], repo, sketch=False, run_id="resolve-1")
        assert run["summary"]["evidence_level"] == "missing", run
        assert run["summary"]["claim_allowed"] == "none", run
        assert not run["summary"]["ready_for_sketch_report"], run
        assert not os.path.exists(os.path.join(run["run_dir"], "sketch.patch"))
        assert run["verifier_resolution"]["status"] == "declared_verifier_missing_sketch_disabled", run


def test_resolve_verifier_pathless_command_is_unconfirmed():
    # #6: a declared verifier with no file-path token (e.g. `make check`, here a -c one-liner)
    # is a real command we can't statically tie to a gate. Run it, but never call it proof.
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)

        case_dir = os.path.join(root, "case")
        created = create_manifest(
            case_dir,
            "https://example.test/repo.git",
            verifier=["echo ok"],   # a real command with NO path token, cross-platform (no .exe path)
            may_touch=["src/"],
            must_not_touch=["secrets/"],
            max_runtime_seconds=60,
        )
        _write_json(os.path.join(case_dir, "answers.json"), ANSWERS)

        run = resolve_verifier(created["manifest_path"], repo, run_id="resolve-pathless")
        assert run["summary"]["verifier_passed"], run            # the command ran and passed
        assert run["summary"]["evidence_level"] == "unconfirmed", run
        assert run["summary"]["claim_allowed"] == "declared_unverified", run
        assert not run["summary"]["ready_for_pr_claim"], run     # a path-less gate is not PR-proof
        assert run["verifier_resolution"]["status"] == "declared_verifier_unconfirmed", run


def test_absent_run_dir_is_missing_evidence():
    # #7: a run dir with no verifier results must fail closed to "missing", never "confirmed_local".
    from super_looper.experimental.case_study import summarize_run
    with open(os.path.join(ROOT, "examples", "nightly-export.loop.json")) as f:
        loop = json.load(f)
    with tempfile.TemporaryDirectory() as run_dir:
        _write_json(os.path.join(run_dir, "loop.json"), loop)   # valid loop, but NO verifier-results.json
        summary = summarize_run(run_dir)
        assert summary["evidence_level"] == "missing", summary
        assert summary["claim_allowed"] == "none", summary
        assert not summary["ready_for_pr_claim"], summary


def test_simulate_shadow_verifier_alias_still_importable():
    # Back-compat: the old "shadow" name remains importable and is the renamed sketch function.
    from super_looper.experimental.case_study import simulate_shadow_verifier, simulate_sketch_verifier
    assert simulate_shadow_verifier is simulate_sketch_verifier


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
