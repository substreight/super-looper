"""Back-compat shim. The case-study harness now lives in
``super_looper.experimental.case_study`` (relegated — see ``SCOPE.md``).

Importing ``super_looper.case_study`` keeps working for one release; prefer the
experimental path. New code should use ``super_looper.runtime`` for the loop driver.
"""
from .experimental.case_study import *  # noqa: F401,F403
from .experimental.case_study import (  # noqa: F401
    CaseStudyError,
    check_scope,
    create_manifest,
    design_case_study,
    render_report,
    resolve_verifier,
    run_case_study,
    simulate_shadow_verifier,
    simulate_sketch_verifier,
    summarize_run,
    verify_run,
    write_reports,
)
