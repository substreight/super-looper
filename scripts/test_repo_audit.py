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
from super_looper.repo_audit import (  # noqa: E402
    audit_repo,
    default_promotion_out_dir,
    _add_gate,
    _classify_command,
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
