#!/usr/bin/env python3
"""Safely remove local packaging/build artifacts before release.

Why this exists: during the 0.7.0 shim-removal work, a stale gitignored
``build/lib`` tree reintroduced deleted top-level shim modules into a wheel.
Release builds must start from clean generated-artifact directories.

Usage:
    python scripts/clean_release_artifacts.py --dry-run
    python scripts/clean_release_artifacts.py --yes
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable, List, Tuple


DEFAULT_TARGETS = (
    "build",
    "dist",
    "src/super_looper.egg-info",
    ".pkg-test",
    ".pkg-cache",
    ".pytest_cache",
)


class SafetyError(RuntimeError):
    """Raised when a cleanup target would escape the repository root."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_under(root: Path, rel: str) -> Path:
    root = root.resolve()
    target = (root / rel).resolve()
    if target == root or root not in target.parents:
        raise SafetyError(f"refusing cleanup target outside repository root: {target}")
    return target


def planned_targets(root: Path, targets: Iterable[str] = DEFAULT_TARGETS) -> List[Path]:
    return [_resolve_under(root, rel) for rel in targets]


def clean(root: Path, *, targets: Iterable[str] = DEFAULT_TARGETS, dry_run: bool = True) -> List[Tuple[str, str]]:
    """Return ``[(action, path)]``; with dry_run=False, remove existing targets."""
    actions: List[Tuple[str, str]] = []
    for path in planned_targets(root, targets):
        if not path.exists():
            actions.append(("missing", str(path)))
            continue
        actions.append(("would_remove" if dry_run else "removed", str(path)))
        if not dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    return actions


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print what would be removed")
    mode.add_argument("--yes", action="store_true", help="actually remove generated artifacts")
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        help="override cleanup target (repeatable, relative to repository root)",
    )
    args = parser.parse_args(argv)

    root = repo_root()
    actions = clean(root, targets=args.targets or DEFAULT_TARGETS, dry_run=not args.yes)
    for action, path in actions:
        print(f"{action}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
