# loop-design

A meta-skill for designing clean, minimal **agentic loops** — and for deciding whether a loop is even warranted (usually it isn't).

> **A loop is a goal plus a gate. The gate is the design.**

An agentic loop runs DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE on its own, until an objective gate passes or a hard limit trips — no human pushing each step. This skill teaches the *principles* (design the verifier first; keep state on disk; set three stop conditions; separate maker from checker), enforces the non‑negotiables with a machine‑checkable spec + validator, and — crucially — defaults to **"don't build a loop."** Talking someone out of an unnecessary loop is a successful use of it.

## What's here
- **`SKILL.md`** — the skill itself (load it into your agent harness).
- **`references/`** — `loop-spec-templates.md` (5 filled templates), `state-and-verification.md` (fresh‑restart vs compaction; the verifier ladder), `failure-modes.md` (what each missing part breaks), `evidence.md` (verified citations).
- **`schemas/loop-spec.schema.json`** — JSON Schema for a loop spec.
- **`scripts/validate_loop_spec.py`** — dependency‑free validator (structural + the skill's judgment lints) and renderer. Importable as `validate(spec) -> (errors, warnings)`.
- **`examples/nightly-export.loop.json`** — a worked, valid spec.
- **`evals/`** — the skill's own gate: labeled scenarios + a deterministic scorer (`EVAL.md`).

## Use it
**As a skill:** point your agent at `SKILL.md` (e.g. drop the folder into your skills directory). Ask it to design — or talk you out of — a loop; it qualifies via Step 0, designs the gate first, and emits a spec.

**Validate a spec:**
```
python scripts/validate_loop_spec.py my-loop.json            # exit 1 on error
python scripts/validate_loop_spec.py my-loop.json --render    # print the human-readable spec
python scripts/validate_loop_spec.py my-loop.json --strict    # warnings are errors
```
Zero‑dependency: uses `jsonschema` if installed, falls back to a built‑in checker.

**Run the eval** (after any edit to the skill):
```
cd evals && python score_eval.py scenarios.jsonl results.example.jsonl --min 0.8   # -> 8/8
```
See `evals/EVAL.md` for producing fresh results from blind agents.

## The one rule
Design the **verifier before the loop body.** If you can't write a gate that automatically fails bad work — and that gates the *deliverable*, not just the plumbing — the task isn't a loop yet. Most tasks aren't.

## Evidence
The load‑bearing claims are sourced in `references/evidence.md` (self‑correction limits, self‑preference bias, context rot, verifiable rewards). The named techniques ("Ralph," evaluator‑optimizer, harnesses) are mostly blog‑evidenced — design from the principles.

## License
MIT — see [`LICENSE`](LICENSE).
