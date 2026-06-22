# Changelog

## 0.6.2 — 2026-06-22
Repo-audit gate hygiene + promotion supplement — driven by dogfooding the audit on 7 fresh public repos (Python/TS/Rust/Go, Makefiles, a monorepo, multi-CI). No crashes anywhere; the routing stayed conservative; the *gate inventory* was the rough edge.

- **Gate hygiene:** drop non-runnable commands (`${{ }}` CI interpolation, backticks, `$(...)`); drop non-verifier tasks (`prepare-release` / `gh-release-notes` / `update-plugin-list` / `bump-version` — these ship releases, they aren't gates); dedupe on a canonical key across sources and normalize `npm|yarn|pnpm run X` → `… X` (so `make test` from three workflows collapses to one, and `yarn run test` merges with `yarn test`).
- **Variant consolidation (#4):** npm/yarn/pnpm script `:`-variants within a category collapse to one representative (the base), with the dropped variants noted in the rationale. On prettier: **42 → 7** gates.
- **Fuzz isn't a strong gate (#5):** `go test -fuzz=… -fuzztime=…` is time-boxed and nondeterministic, so it's tagged `test|weak`, not `test|strong`.
- **Promotion `--answers` supplement:** `super-looper repo promote --answers human.json` merges human answers over the lead-derived ones, so a human can fill the gaps a static scan can't know and a borderline lead can qualify into a real loop (still gated by the verdict engine).

## 0.6.1 — 2026-06-22
The live skill gate goes on — plus the fixes and skill sharpening it immediately surfaced.

- **The skill gate is live.** CI now runs the actual `SKILL.md` blind over the scenarios on Opus (push-to-`master` + nightly, secret-gated) and passes at **9/10**. The first real runs caught three CI bugs *and* one genuine skill improvement the old frozen eval never could.
- **CI fixes:** drop the deprecated `temperature` arg (Opus 4.8 rejects it); install `pytest` for the case-study harness's subprocess gate; make the path-less verifier test cross-platform.
- **Skill sharpening — gate-gaming:** a gate the maker can satisfy by *weakening the check* ("make the suite green" → delete the test) isn't a `REJECT_DESIGN`, it's a **guarded** loop — pin the gate to the *unmodified* check and fence the test files (`must_not_touch`). Added to `SKILL.md` and `references/failure-modes.md`.
- **Eval calibration:** corrected over-precise answer keys the live run exposed — `DISCOVERY_REQUIRED` accepted for an unattended/no-gate task, the `fix-tests` scenario rewritten as a genuinely clean loop, and `REJECT_DESIGN` accepted for a subjective one-off.

## 0.6.0 — 2026-06-22
**Back to center:** the loop as a deterministic primitive, an honest validator, and a relegated perimeter. The north star — *determinism → code, judgment → the model, infrastructure → the environment.*

**Core — make the loop first-class:**
- **Loop driver (`super_looper.runtime.run_loop`):** a tiny deterministic executor that runs a validated loop's skeleton *in code* — iteration/budget/no-progress caps, the keep/revert ratchet, state checkpointing — with the model's `propose` step, the gate, the workspace, and the clock all **injected**. `super-looper run <spec> --propose <cmd> --verify <cmd>` drives it. No LLM/network/subprocess of its own; fail-closed (only an explicit pass keeps).
- **Execution policy:** `execution.untrusted` + `execution.policy {host_credentials, network{setup,verification}, artifacts}`. A loop that runs untrusted code must declare a coherent isolation policy before it runs; the validator refuses without it — but super-looper never owns the sandbox.

**Validator honesty (the core stops lying):**
- Gate quality caps the autonomy ceiling — a weasel/taste gate can no longer earn L3.
- The zero-dependency checker rejects typo'd/unknown keys (budget + the new policy object).
- Vacuous gates route to `DISCOVERY_REQUIRED`; the compiler no longer fabricates `verifier.end_to_end`.
- The interview now elicits every signal its own classifier branches on.

**Evidence discipline:**
- Shadow verifiers reframed as **verifier sketches** — a proposal that appears viable, never proof; a sketch can never reach a PR-ready claim (back-compat aliases kept one release).
- New `unconfirmed` evidence tier: a path-less verifier command (e.g. `make check`) runs but is never proof; absent/partial runs fail closed to `missing`.

**Repo-audit → qualifying intake adapter:**
- Speaks **automation leads** (`automation-leads.json`; `loop-hypotheses.json` kept as an alias) — a lead is intake, not a loop. Promotion emits a loop spec only on a real qualification verdict; unqualified leads stay discovery packets.
- Word-boundary gate matching (`latest` no longer matches `test`).
- `super-looper repo promote` turns one candidate into a clean case-study proof packet (`case-study.json`, `inputs/`, `design/`, `proof/`, `reports/`).

**Project hygiene / relegation:**
- CI now invokes the **actual skill** blind over each scenario (Opus, secret-gated) instead of scoring a frozen file; it runs all test modules; the frozen file is a clearly-labeled scorer self-test.
- The case-study harness and the remote-runner transport are relegated to `super_looper/experimental/` (back-compat shims kept); the CLI lazy-loads the perimeter so `validate`/`run`/`explain`/`max-autonomy` load **none** of it.
- The remote-runner plan no longer asserts security controls it doesn't enforce (`isolation_enforced` / `not_enforced_here` make advisory-vs-enforced explicit).

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
