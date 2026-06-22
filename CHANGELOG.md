# Changelog

## 0.6.0 - unreleased
Candidate promotion proof packets.

- **Repo candidate promotion:** added `super-looper repo promote` to turn one audit candidate into a case-study proof packet.
- **Clean taxonomy:** promotion writes `case-study.json`, `inputs/`, `design/`, `proof/`, and `reports/` with stable names for downstream review, remote runs, and maintainer sharing.
- **Safe hypothesis handling:** creative repo hypotheses remain discovery packets and intentionally do not receive `design/loop.json` until verifier evidence exists.
- **Default naming convention:** when `--out` is omitted, promotion writes to `case-studies/<repo-slug>/<candidate-slug>/`; `--out-root` keeps the convention under a different root.
- **Gate-only hardening:** repair candidates found from static repo files now stay `discovery_required` with `static_gate_only` evidence until failing lint/typecheck output, a real failing check, repeated failure signature, dependency-bump failure, flaky-test history, or maintainer task proves there is an actionable loop.

## 0.5.0 — 2026-06-21
Repository automation discovery + loop hypotheses.

- **Repo discovery:** added `super-looper repo audit` to inventory repo-native gates, rank automation candidates, and route each candidate to `plain_scheduler`, `human_in_loop`, `l2_candidate`, `discovery_required`, or `do_not_automate` instead of auto-generating loops.
- **Repo audit reports:** added machine-readable gate/candidate JSON plus `ranked-backlog.md` and `recommendations.md` outputs for sharing conservative automation findings with maintainers.
- **Repo-specific surfaces:** added `repo-surfaces.json` and surface-linked candidates so audits can recommend bounded workflow/test-suite/code-quality opportunities instead of only whole-repo templates.
- **Loop hypotheses:** added `loop-hypotheses.json` and report sections for creative but explicitly unproven opportunities such as flaky CI triage, example smoke tests, integration drift, CLI contracts, release smoke checks, and performance watchpoints.
- **Automation allocator docs:** added `references/repo-discovery.md` and updated `SKILL.md`/`README.md` to position Super Looper as an agentic design linter and autonomy allocator before runtime loop design.

## 0.4.0 — 2026-06-21
Installable CLI package.

- **Package layout:** moved validator and interview compiler logic into `src/super_looper/` with importable APIs and bundled schema resources.
- **Console command:** added `super-looper` with `questions`, `interview`, `validate`, `render`, `explain`, and `max-autonomy` subcommands.
- **Compatibility:** kept `scripts/validate_loop_spec.py` and `scripts/design_loop.py` as thin wrappers so existing repo-local commands still work.
- **Packaging:** added `pyproject.toml`, optional `jsonschema` extra, package metadata, and build artifact ignores.
- **CI:** added GitHub Actions coverage for script tests, behavioral evals, package install, and packaged CLI smoke tests.
- **Case studies:** added a dependency-free `super-looper case-study` harness with manifest creation, design compilation, local verifier runs, diff/scope guards, run summaries, and maintainer/PR markdown reports.
- **Shadow verifiers:** added `case-study simulate-verifier` for proposing and running verifier tests from artifacts without modifying the target checkout; reports now distinguish shadow evidence from upstream verification.
- **Verifier resolution:** added `case-study resolve-verifier`, which prefers confirmed repo-local gates and falls back to shadow verifiers by default; `--no-shadow` reports missing gates without generating proposals.
- **Headroom example:** added a real-repo Headroom AST-compression loop design fixture, manifest, and write-up; it compiles to a clean L2 spec and documents why L3 is not yet earned.
## 0.3.0 — 2026-06-21
Unknown-safe compiler + stricter autonomy enforcement.

- **Unknown answers become `DISCOVERY_REQUIRED`:** the skill now treats "I don't know" as L0 evidence-gathering work, not a reason to guess. Added `scripts/design_loop.py`, a zero-dependency interview/spec compiler that emits a discovery plan when critical answers are missing and writes a draft JSON spec only when the facts are concrete enough.
- **No false L3:** `max_autonomy(spec)` now requires L2 specs to have a real automatic gate, `scope.must_not_touch`, and `stop_conditions.budget`; L3 additionally requires an unattended trigger, end-to-end rung-1 tool gate, explicit reversible output, and `autonomy.proven_manual_pass: true`.
- **Manual proof separated from cost proof:** `autonomy.proven_manual_pass` is now a schema field, separate from `economics.proven_cheap`.
- **Zero-dependency fallback hardened:** the built-in structural checker now validates the scalar and container types that semantic lint relies on, preventing malformed specs from crashing fallback validation.
- **Tests/examples:** added interview answer fixtures and standalone tests for the compiler and autonomy bypass regressions.

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
