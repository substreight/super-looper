"""Experimental Super Looper subsystems — NOT the core.

These are perimeter pieces relegated here on purpose: the
case-study repo/diff/mini-CI harness and the remote-runner *transport*. The core
of Super Looper is the loop primitive (definition, the deterministic driver,
boundaries, state) plus the verdict/autonomy judgment — none of which lives here.

The genuinely-useful lessons from this code are expressed as core requirements:
- *where it runs* → ``execution.policy`` in the loop spec (the validator checks it;
  your own infrastructure enforces it). Super Looper does not own the sandbox.
- *the deterministic loop skeleton* → ``super_looper.runtime`` (the core driver).
- *evidence discipline* → "a sketch/unconfirmed run is never proof" (case_study).

Treat everything here as deprecated/experimental and replaceable.
"""
