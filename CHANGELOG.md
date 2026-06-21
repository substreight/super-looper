# Changelog

## 0.1.0 — 2026-06-21
First packaged release.

- **Core skill (`SKILL.md`):** Step 0 qualification, the verifier ladder, state architecture (fresh‑restart vs compaction), three stop conditions, maker ≠ checker, the canonical + JSON spec, cost discipline, the harness, build order.
- **Decision discipline:** the **gate‑covers‑the‑deliverable** test, the **time‑trigger → scheduler** rule, `USE_SCHEDULER` as a first‑class verdict, the "needs judgment ≠ autonomous loop" sharpening, **human decision points**, and the **proposal output contract** (uniform structure, ranked, curated by the human — include/exclude as well as re‑rank).
- **Validator (`scripts/validate_loop_spec.py`) + schema:** structural checks plus semantic lints — self‑grading off the ladder, unattended‑with‑no‑gate, unattended‑with‑no‑budget, parallelism‑without‑isolation, weasel/measurable/coherence gate‑quality, single‑pass `max_iterations: 1`. Dependency‑free with graceful fallback when `jsonschema` or the schema file is absent. 20 tests.
- **Templates 4 & 5:** invariant → self‑verifying regression‑test backfill; gate‑coverage strengthener.
- **`references/evidence.md`:** verified citations for the load‑bearing claims.
- **`evals/`:** the skill's own regression gate — 8 labeled scenarios + a deterministic scorer; baseline 8/8.
