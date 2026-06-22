#!/usr/bin/env python3
"""The minimal CLI path must stay minimal: `super-looper validate` must NOT load the
perimeter (the experimental case-study harness / remote-runner transport, or the
repo-audit engine). Verified in a fresh subprocess so sys.modules is clean.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
EXAMPLE = os.path.join(ROOT, "examples", "nightly-export.loop.json")

_PROBE = """
import sys
sys.path.insert(0, {src!r})
from super_looper.cli import main
main(["validate", {spec!r}])
hot = sorted(m for m in sys.modules if (
    m.startswith("super_looper.experimental")
    or m in ("super_looper.repo_audit", "super_looper.case_study", "super_looper.remote_runner")
))
sys.stderr.write("PERIMETER=" + ",".join(hot) + "\\n")
"""


def _perimeter_loaded_by_validate():
    code = _PROBE.format(src=SRC, spec=EXAMPLE)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        if line.startswith("PERIMETER="):
            return line.split("=", 1)[1]
    raise AssertionError(f"probe did not report (stdout={proc.stdout!r} stderr={proc.stderr!r})")


def test_validate_does_not_import_perimeter():
    loaded = _perimeter_loaded_by_validate()
    assert loaded == "", f"the validate path loaded perimeter modules: {loaded}"


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
