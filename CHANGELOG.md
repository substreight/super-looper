# Changelog

## 0.2.0 — 2026-06-21
Autonomy dial + friendliness on-ramps.

- **Autonomy dial (L0–L3):** autonomy is *earned, not chosen*. New `## Autonomy levels` section in `SKILL.md`; the validator computes the earned ceiling — `max_autonomy(spec)` — from gate rung + budget + scope fence + output reversibility + a proven manual pass, and **errors when `autonomy.requested` exceeds it**, naming what's missing. New optional `autonomy` block in the schema (`requested`, `output_reversibility`).
- **Friendliness on-ramps (`SKILL.md`):** a 6-question *guided design interview* (qualify without making the user read the skill), a *plain-language preview* (`validate_loop_spec.py --explain` → one jargon-free sentence + `render_plain()`), an explicit *dry-run (L0)* first step in Build order, and a *helpful-refusal* contract (always pair the why with the concrete alternative + what unlocks more).
- **Tests/eval:** +10 validator tests (30 total); +1 eval scenario (`unattended-no-gate`), baseline 9/9.

## 0.1.0 — 2026-06-21
First packaged release.

- **Core skill (`SKILL.md`):** Step 0 qualification, the verifier ladder, state architecture (fresh‑restart vs compaction), three stop conditions, maker ≠ checker, the canonical + JSON spec, cost discipline, the harness, build order.
- **Decision discipline:** the **gate‑covers‑the‑deliverable** test, the **time‑trigger → scheduler** rule, `USE_SCHEDULER` as a first‑class verdict, the "needs judgment ≠ autonomous loop" sharpening, **human decision points**, and the **proposal output contract** (uniform structure, ranked, curated by the human — include/exclude as well as re‑rank).
- **Validator (`scripts/validate_loop_spec.py`) + schema:** structural checks plus semantic lints — self‑grading off the ladder, unattended‑with‑no‑gate, unattended‑with‑no‑budget, parallelism‑without‑isolation, weasel/measurable/coherence gate‑quality, single‑pass `max_iterations: 1`. Dependency‑free with graceful fallback when `jsonschema` or the schema file is absent. 20 tests.
- **Templates 4 & 5:** invariant → self‑verifying regression‑test backfill; gate‑coverage strengthener.
- **`references/evidence.md`:** verified citations for the load‑bearing claims.
- **`evals/`:** the skill's own regression gate — 8 labeled scenarios + a deterministic scorer; baseline 8/8.
