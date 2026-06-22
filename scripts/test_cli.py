#!/usr/bin/env python3
"""Smoke + behavior tests for the core CLI surface (super-looper).

Covers the new everyday entry points: bare invocation prints the golden path,
`check` returns the right exit code and card, and `check --json` is structured.
Runs under pytest, or standalone:  python test_cli.py
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.cli import build_parser, main as cli_main  # noqa: E402

GOOD = os.path.join(ROOT, "examples", "nightly-export.loop.json")
UNKNOWN_ANSWERS = os.path.join(ROOT, "examples", "unknown-gate.answers.json")


def _capture(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli_main(argv)
    return rc, buf.getvalue()


def test_bare_invocation_prints_golden_path_and_exits_zero():
    rc, out = _capture([])
    assert rc == 0
    assert "Start here:" in out
    assert "super-looper decide" in out
    assert "super-looper check" in out
    assert "super-looper lab repo audit" in out


def test_check_passes_clean_spec():
    rc, out = _capture(["check", GOOD])
    assert rc == 0
    assert out.startswith("CHECK PASSED")
    assert "max safe:   L3" in out


def test_check_json_is_structured():
    rc, out = _capture(["check", GOOD, "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["max_autonomy"] == "L3"
    assert payload["requested_autonomy"] == "L3"


def test_check_fails_when_requested_autonomy_exceeds_earned():
    # Demoting the gate to independent_model drops earned to L2 while the spec still
    # requests L3 -- the validator treats this as an error, so check must exit nonzero
    # and the card must flag the requested level as too high.
    import tempfile
    with open(GOOD, encoding="utf-8") as f:
        spec = json.load(f)
    spec["verifier"] = dict(spec["verifier"], rung="independent_model", end_to_end=False)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "loop.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f)
        rc, out = _capture(["check", path])
        assert rc == 1
        assert "CHECK FAILED" in out
        assert "requested:  L3 (TOO HIGH)" in out
        assert "max safe:   L2" in out


def test_decide_defaults_to_human_first_card():
    rc, out = _capture(["decide", "--answers", UNKNOWN_ANSWERS])
    assert rc == 0
    assert out.startswith("DISCOVERY REQUIRED")
    assert "Answer before continuing:" in out
    assert "Next discovery steps:" in out


def test_decide_json_preserves_machine_shape():
    rc, out = _capture(["decide", "--answers", UNKNOWN_ANSWERS, "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert payload["report"]["verdict"] == "DISCOVERY_REQUIRED"


def test_doctor_runs_without_network_and_reports_core_status():
    rc, out = _capture(["doctor"])
    assert rc == 0
    assert out.startswith("SUPER-LOOPER DOCTOR")
    assert "perimeter loaded in this process:" in out


def test_lab_repo_audit_dispatches_to_existing_perimeter_command():
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "tests"))
        with open(os.path.join(root, "tests", "test_smoke.py"), "w", encoding="utf-8") as f:
            f.write("def test_smoke():\n    assert True\n")
        rc, out = _capture(["lab", "repo", "audit", "--repo-path", root])
    assert rc == 0
    assert "repo audit complete" in out
    assert "candidates:" in out


def test_top_level_help_shows_core_plus_lab_not_legacy_perimeter_aliases():
    help_text = build_parser().format_help()
    assert "doctor" in help_text
    assert "lab" in help_text
    assert "==SUPPRESS==" not in help_text
    assert "repo                " not in help_text
    assert "case-study          " not in help_text
    assert "runner              " not in help_text


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
