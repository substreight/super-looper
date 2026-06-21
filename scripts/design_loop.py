#!/usr/bin/env python3
"""Compatibility wrapper for the packaged interview/spec compiler."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from super_looper.design import *  # noqa: E402,F401,F403
from super_looper.design import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main(sys.argv))
