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
from super_looper.repo_audit import audit_repo  # noqa: E402


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
    assert ci["recommended_path"] == "l2_candidate"
    assert ci["max_agent_autonomy"] == "L2"
    assert "one proven manual pass" in " ".join(ci["missing_evidence"])
    surface_candidates = [candidate for candidate in audit["automation_candidates"] if candidate.get("surface_id")]
    assert any(candidate["surface_id"].startswith("ci-workflow") for candidate in surface_candidates)
    assert any("workflow `.github/workflows/ci.yml`" in candidate["title"] for candidate in surface_candidates)
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
