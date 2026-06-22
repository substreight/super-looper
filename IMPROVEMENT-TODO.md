# super-looper — Plan & Technical TODO: Shrink the Center, Stop Expanding the Perimeter

**Date:** 2026-06-21 · **Reads with:** [`SCOPE.md`](./SCOPE.md) (north star) · [`REVIEW-2026-06-21.md`](./REVIEW-2026-06-21.md) (evidence)
**Status:** Plan for review. Nothing here is implemented yet. This is the cohesive plan requested *before* execution.

---

## The vision in one paragraph

The work so far taught us where the real product is. Super Looper's value is **judging loops** — verdict, spec, gate, earned-autonomy ceiling — not running them. So we **shrink to that center and make it honest**, keep discovery as a **summonable intake adapter** (not the center), turn the VPS/runner ambition into **policy the spec emits** (not infrastructure we own), and reframe shadow verifiers as **sketches, never proof**. Then we fix the major holes that let the center lie (a taste gate earning L3; a typo'd budget cap passing; the project's own gate unable to fail its own work). The result is ~1k LOC that does the one unique thing, surrounded by thin, labeled adapters.

---

## Roadmap (the 6 points, sequenced)

| # | Roadmap point | Phase |
|---|---|---|
| 1 | Define core/non-core boundaries in `SCOPE.md` | **Phase 0 — done in this plan** |
| 2 | Re-cut TODO around "cleave policy from transport" | **Phase 0 — this document** |
| 3 | Move runner/case-study plumbing to experimental/deprecated | Phase 2 |
| 4 | Keep only thin adapters that emit specs/policies existing infra can consume | Phase 2 |
| 5 | Tighten repo-audit language from "candidate loop" → "automation lead" | Phase 2 |
| 6 | Make promotion require core qualification, not static repo evidence | Phase 2 |
| + | Fix the major breaks/holes in the core | **Phase 1 (first code)** |

**Order of execution:** Phase 1 (re-arm + dogfood the core) → Phase 2 (cleave & reframe the perimeter) → Phase 3 (de-bloat & hygiene). Rationale: the center must be trustworthy *before* we restructure around it, and the Phase-1 fixes are small, surgical, and independent of the reorg.

**What NOT to do:** no new subsystems, templates, or provider integrations until Phase 1 is green. Quarantine before delete (capture the lesson as a spec requirement first).

---

## Phase 1 — Re-arm the core and make it pass its own gate *(first code; do these together)*

> Goal: the validator enforces what the prose promises, and CI can fail the skill's own work.

### ☑ 1.1 — Gate quality must cap the autonomy ceiling  *(was A1 · P0 · S)* — ✅ DONE (TDD)
- **Problem:** A "taste" gate earns L3. `max_autonomy()` reads only structural fields; the `_weasel`/`_MEASURABLE` quality lints are warnings-only and the ceiling never consults them.
- **Evidence:** `validate.py:99-149` vs `461-476`, `486-493`. `verifier.rung:"tool"` + `check:"the report looks good"` + L3 request ⇒ `errors=[]`, ceiling `L3`.
- **Fix:** In `max_autonomy`, when `rung in {tool, independent_model}` and `verifier.check` is a weasel phrase **or** has no `_MEASURABLE` token, cap the earned ceiling at **L1** and append the reason to `missing`. Keep quality advisory at L0/L1; only bind it where autonomy is requested.
- **Test:** weasel-gate L3 spec ⇒ blocking error + `max_autonomy == "L1"`. **This is the smolagents fix.**

### ☑ 1.2 — Reject unknown/typo'd keys in the zero-dep checker  *(was A2 · P0 · S–M)* — ✅ DONE (builtin checker; schema-side `additionalProperties:false` parity still open)
- **Problem:** `budget:{"max_runtim_seconds":1800}` passes the built-in checker with `errors=[]`; non-empty dict also suppresses the "no budget cap" error. Misspelled cap = silent no-op in zero-dep mode.
- **Evidence:** `validate.py:310-321, 441-444` (the jsonschema path rejects it; the fallback doesn't — the two disagree).
- **Fix:** Derive a per-object key allowlist from the schema `properties`; `_builtin_structural` rejects unknown keys for `budget`/`verifier`/`scope`/`stop_conditions`/`autonomy`. Add a **parity test**: a typo corpus must produce identical verdicts on both structural paths.

### ☑ 1.3 — A vacuous gate is treated like "I don't know"  *(was A4 · P1 · S–M)* — ✅ DONE (TDD)
- **Problem:** `gate_check:"it works"` compiles to `AUTONOMOUS_LOOP`; the unknown-field check only catches literal unknown-word tokens.
- **Evidence:** `design.py:164-169, 241-253`; `UNKNOWN_WORDS:42-45`.
- **Fix:** Treat a gate as insufficiently concrete (→ `DISCOVERY_REQUIRED`, or at least non-autonomous) when it's a weasel phrase or has no `MEASURABLE` token and names no path/tool. Reuse the `_is_subjective`/`MEASURABLE` machinery already present.

### ☑ 1.4 — Stop fabricating `end_to_end`; require explicit L3 attestation  *(was A3 · P1 · S)* — ✅ DONE (TDD)
- **Problem:** `build_spec` defaults `verifier.end_to_end=True` for tool gates, manufacturing one of the four L3 attestations.
- **Evidence:** `design.py:283, 315`.
- **Fix:** Default `end_to_end` to `False`/`None` when absent; only true on explicit attestation; surface the resulting `missing`.

### ☑ 1.5 — Reconcile the interview with the classifier's own signals  *(was E1 · P1 · M)* — ✅ DONE (added the 4 missing decision questions + made `agent_can_do_end_to_end` robust to string answers; TDD)
- **Problem:** The interactive interview never asks `deterministic_without_llm` / `self_grading` / `agent_can_do_end_to_end` / `unattended`, yet `classify_answers` branches on exactly those — so `USE_SCHEDULER` / `REJECT_DESIGN` / unattended-`HUMAN_IN_LOOP` can't fire interactively. The "you don't have to read the skill" promise is hollow.
- **Evidence:** `design.py:31-40` vs `196/214/223/232`, `363-367`.
- **Fix:** Add the missing questions to `QUESTIONS` (mapped to the classifier keys) or derive them from existing answers. Test: the interview elicits every key any branch consults.

### ☑ 1.6 — CI must invoke the skill  *(was B1 · P0 · M)* — ✅ DONE (blind runner `evals/run_skill_eval.py` + unit tests; secret-gated `skill-eval` CI job on Opus, push-to-main/nightly/manual; frozen file relabeled `results.sample.jsonl` as a scorer self-test). **Activation:** add the `ANTHROPIC_API_KEY` repo secret to turn the live gate on.
- **Problem:** The "behavioral eval" scores a frozen, hand-authored `results.example.jsonl`. `SKILL.md` is never invoked in CI; a broken skill stays green.
- **Evidence:** `ci.yml:28-29`; `score_eval.py:4-6`.
- **Fix:** Add an opt-in, API-keyed CI job that spawns a **blind agent** over `SKILL.md` per scenario and scores *that* output. Rename the frozen-file scorer (e.g. `score_recorded.py`) so it can't be mistaken for the live gate. Keep the deterministic scorer; change only what produces the results.

### ☑ 1.7 — Run every test module in CI + coverage floor on risky modules  *(was B2 · P0 · S)* — ✅ run-all-5-modules DONE (verified stdlib-only, self-pathing, `from __future__ import annotations` for 3.9); coverage floor deferred (needs `pytest-cov`, folded into the 1.6 tooling decision)
- **Problem:** Only `test_validate`/`test_design` run; `test_case_study`/`test_remote_runner`/`test_repo_audit` (~3,400 LOC incl. the security surface) never run.
- **Evidence:** `ci.yml:22-29`.
- **Fix:** `python -m pytest scripts/ -q` (or list all five) + a coverage floor weighted on `repo_audit.py` / `remote_runner.py`.

---

## Phase 2 — Cleave policy from transport (reshape the perimeter)

> Goal: extract the unique policy the perimeter taught us; outsource/quarantine the non-unique transport; relabel discovery as intake.

### ☐ 2.1 — Extract the execution policy into the spec/schema  *(P1 · M)*
- **Do:** Add an `execution.isolation` + `execution.policy` block to the schema: `host_credentials:"none"`, `network_during_verification:"off"`, `artifacts:"allowlist"`. `max_autonomy` **requires a coherent policy for L2+/L3** and refuses without it.
- **Why:** This is the genuinely-unique core inside `remote_runner` — the *requirement*, not the SSH. Captures the VPS lesson as a spec rule. (`SCOPE.md` → "Policy, not infrastructure".)
- **Test:** an unattended/L3 spec without the policy is refused with a named `missing`.

### ☐ 2.2 — Quarantine the runner transport; deprecate, don't delete  *(roadmap #3 · P1 · S)*
- **Do:** Move `remote_runner.py` behind an `experimental` import / `super-looper experimental runner …` namespace; print a deprecation note pointing to the execution-policy spec. **Do this only after 2.1 captures the policy.**
- **Why:** Keep the lessons; stop presenting bespoke SSH/container orchestration as the product. (`SCOPE.md` → Quarantine.)
- **Also closes:** the C1/C2 security gaps (asserted-but-unenforced network/artifact controls) become moot once we stop emitting an owned runner.

### ☐ 2.3 — Reframe shadow verifiers as sketches, never proof  *(P1 · M)*
- **Do:** Rename in code + reports: `shadow verifier` → **`verifier_sketch` / discovery artifact**. A sketch result is `evidence_level:"sketch"` and **cannot** reach any "ready"/"confirmed" claim (assert this with a test). Drop the fake one-template "framework" abstraction; keep the concept.
- **Evidence/why:** `case_study.py` shadow path + `_declared_verifier_status:309-330` (a path-less command currently self-certifies). Shadow-as-evidence is the maker==checker relapse. (`SCOPE.md` → Evidence discipline / Discard.)
- **Test:** a passing sketch never yields `ready_for_pr_claim`/`confirmed_local`.

### ☐ 2.4 — Quarantine the case-study run/diff/report harness; keep the evidence ladder  *(roadmap #3,#4 · P2 · M)*
- **Do:** Extract the evidence-ladder semantics into spec/validator language; move the run/diff/packaging harness behind `experimental`. Fix the fail-open default first: absent/partial run dir ⇒ `evidence_level:"missing"`, not the strongest tier.
- **Why:** Case-study value is *evidence discipline*, not a mini-CI runner. (`SCOPE.md`.)

### ☐ 2.5 — Repo audit → Repo Discovery **Adapter**: "automation lead," not "candidate loop"  *(roadmap #5 · P1 · S–M)*
- **Do:** Rename the user-facing taxonomy and report language from "candidate loop"/"loop hypotheses" to **"automation lead."** Keep it summonable (`super-looper repo audit …`). State in output that a lead is *intake*, not a loop.
- **Why:** Identity = intake adapter, not center. Static scan must never *look like* it produced a loop. (`SCOPE.md` → Adapters.)

### ☐ 2.6 — Promotion requires core qualification, not static evidence  *(roadmap #6 · P1 · M)*
- **Do:** `repo promote <lead>` must run the lead through the **verdict engine** (`classify_answers`/`max_autonomy`) and may emit a `design/loop.json` **only** when it qualifies. Static repo evidence (a CI file exists) never grants autonomy or a loop spec.
- **Evidence/why:** today promotion can mint design artifacts from repo evidence; `repo_audit.py:1738-1741` already hard-wires "static audit never grants L3" — extend that to "static audit never grants a loop." Closes the gap that produced over-confident leads.
- **Test:** a lead with a CI file but no qualifying gate promotes to a **discovery packet**, not a loop spec.

---

## Phase 3 — De-bloat & hygiene (make minimalism true, mechanically)

### ☐ 3.1 — Single-source the autonomy ladder and `MEASURABLE` regex  *(P2 · M)*
`build_spec` should *call* `max_autonomy` instead of re-deriving the ladder (`design.py:274-285`); export one `MEASURABLE` (`validate.py:64` / `design.py:52`). One definition of "earned," so Phase-1 fixes don't have to be applied three times.

### ☐ 3.2 — Lazy per-subcommand CLI imports  *(P2 · S)*
`super-looper validate` must not import the audit engine or runner. Import inside each handler so the minimal path stays minimal. (`cli.py` top-level imports.)

### ☐ 3.3 — Collapse `repo_audit.py` imagined-candidate stanzas to a table  *(P3 · M)*
~480 lines of identical prose literals → a dataclass table + one emit loop (~300 LOC removed), making the largest/least-tested module legible.

### ☐ 3.4 — `must_mention` word-boundary match + diagnostics  *(P2 · S)*
`score_eval.py:45-47`: `\bword\b` not substring; emit a per-scenario diagnostic when the verdict is right but the rationale misses.

### ☐ 3.5 — Release/state hygiene + gate it  *(P1–P2 · S–M)*
Commit/stash the dirty tree; backfill the `v0.4.0` tag; sync `pyproject`/`__init__` version with the documented surface; add a check that fails release if the tree is dirty or docs reference a version ahead of `__init__.__version__`.

### ☐ 3.6 — `isatty` guard on interactive `input()`  *(P2 · S)*
`design.py:366`: non-TTY + no `--answers` ⇒ clean "provide --answers" error, not `EOFError`.

### ☐ 3.7 — README/SKILL ordering  *(P2 · S)*
Lead with the refusal-first message and the core; move the five CLI subsystems below it. Make "minimal" true at first contact.

---

## Definition of done (the project's own gate, applied to this effort)

The work is "back to center" when **all** hold:
1. A weasel/taste gate cannot earn above L1 (1.1) and a typo'd cap cannot pass (1.2). *(The core stops lying.)*
2. CI invokes `SKILL.md` and runs every test module (1.6, 1.7). *(The project passes its own gate.)*
3. No spec earns L2+/L3 without a coherent execution policy, and super-looper owns no transport (2.1, 2.2). *(Policy, not infrastructure.)*
4. No shadow result can reach a "ready/confirmed" claim, and promotion requires qualification (2.3, 2.6). *(No self-grading; no static-evidence loops.)*
5. Repo audit speaks "automation lead," summonable, clearly intake (2.5). *(Adapter, not center.)*
6. The autonomy ladder has exactly one source of truth (3.1), and `validate` doesn't import the perimeter (3.2). *(Minimal is mechanical, not aspirational.)*

---

## Proposed first move

Phase 1 items **1.1, 1.2, 1.3, 1.4** are surgical, independent of the reorg, test-first, and directly close the holes that let the center lie (including the smolagents faceplant). I'll implement them TDD against the current tree on your go, then 1.6/1.7 to make the gate real, then open Phase 2.
