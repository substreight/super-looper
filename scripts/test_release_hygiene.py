#!/usr/bin/env python3
"""Tests for release artifact cleanup safety."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import clean_release_artifacts as c  # noqa: E402


def test_clean_dry_run_does_not_remove_existing_target():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "build"))
        actions = c.clean(c.Path(d), targets=["build"], dry_run=True)
        assert actions == [("would_remove", os.path.join(d, "build"))]
        assert os.path.isdir(os.path.join(d, "build"))


def test_clean_yes_removes_existing_target_under_root():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "dist"))
        actions = c.clean(c.Path(d), targets=["dist"], dry_run=False)
        assert actions == [("removed", os.path.join(d, "dist"))]
        assert not os.path.exists(os.path.join(d, "dist"))


def test_clean_reports_missing_target():
    with tempfile.TemporaryDirectory() as d:
        actions = c.clean(c.Path(d), targets=["build"], dry_run=False)
        assert actions == [("missing", os.path.join(d, "build"))]


def test_cleanup_target_must_stay_under_root():
    with tempfile.TemporaryDirectory() as d:
        try:
            c.planned_targets(c.Path(d), ["../outside"])
        except c.SafetyError:
            pass
        else:
            raise AssertionError("cleanup target escaped root but was accepted")


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
