#!/usr/bin/env python3
"""Compatibility wrapper for the packaged validator."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper import validate as _validate_fn  # noqa: E402,F401
from super_looper.validate import *  # noqa: E402,F401,F403
from super_looper.validate import _builtin_structural, _main, _semantic  # noqa: E402,F401


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
