"""Super Looper package API."""

from .design import build_spec, classify_answers, render_decision
from .runtime import RunResult, run_loop
from .validate import max_autonomy, render, render_check, render_plain, validate

__version__ = "0.7.5"

__all__ = [
    "__version__",
    "build_spec",
    "classify_answers",
    "render_decision",
    "max_autonomy",
    "render",
    "render_check",
    "render_plain",
    "run_loop",
    "RunResult",
    "validate",
]
