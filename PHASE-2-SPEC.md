# Phase 2 Spec — Cleave Policy from Transport

**Date:** 2026-06-21 (rev 2, post self-review) · **Reads with:** [`SCOPE.md`](./SCOPE.md), [`IMPROVEMENT-TODO.md`](./IMPROVEMENT-TODO.md), [`REVIEW-2026-06-21.md`](./REVIEW-2026-06-21.md)
**Status:** Approved design, not yet implemented. Phase 1 (1.1–1.7) is complete and green (89 tests).

**Theme:** keep the unique *policy/judgment* the perimeter taught us; relegate the non-unique *transport/plumbing* to clearly-labeled adapters. **Ordering principle:** a lesson becomes a clean spec requirement *before* the code that taught it is quarantined.

**What Phase 2 does — and doesn't.** It shrinks the center's **identity and prominence** (the perimeter becomes adapters/policy/`experimental/`), and makes the remaining honesty gaps mechanical. It does **not** delete much LOC — quarantine-by-move keeps the code in the repo. Actual deletion stays a later, evidence-gated decision once the relegated code is proven unnecessary. "Back to roots" here means *shape and honesty*, not line count.

**The one addition.** Phase 2 *adds* exactly one thing to the center: the **loop driver** (2.4) — the tiny deterministic skeleton that pulls execution + state out of the prompt and makes the loop *runnable*, not merely described. That is the unique primitive the whole effort is about (see `SCOPE.md` north star: *determinism → code, judgment → the model, infrastructure → the environment*). We add a little to the center and subtract a lot from the perimeter.

**Locked decisions:**
1. Execution policy is **untrusted-gated**, and the missing-policy check is a **hard error only when the loop will run** (`autonomy.requested ≥ L1` or a trigger is present); a **warning at L0** (advise-only).
2. The policy's network field is **split**: `network: { setup: on|off, verification: on|off }` — coherence requires `verification == "off"`; `setup` may be on (deps often need it).
3. Quarantine by **moving to `super_looper/experimental/`** (+ CLI `experimental` group), not deleting.
4. The repo-audit rename ships **with a back-compat alias** for the JSON output filename (one release).

Every change is TDD (RED → GREEN) with a paired regression guard. Phase 2 is **breaking** → it closes on a `0.6.0` release (§close-out) and a README/SKILL re-lead.

**Backward compatibility:** existing `.loop.json` specs lack `execution.untrusted`/`policy`; they remain valid (untrusted defaults false → no policy required). 2.1 is additive.

---

## 2.1 — Execution policy into the spec ✅ DONE  *(additive · folded in schema-sync · TDD, 10 gates)*

**Goal:** a loop that runs untrusted code must *declare* an isolation policy; the validator refuses without it when it will run; super-looper never owns the runner.

**Files:** `schemas/loop-spec.schema.json` **and** `src/super_looper/resources/loop-spec.schema.json` (both), `src/super_looper/validate.py`, `examples/untrusted-suite.loop.json`, `scripts/test_validate_loop_spec.py`.

**Schema — extend `execution`:**
```jsonc
"untrusted": { "type": "boolean" },
"policy": {
  "type": "object", "additionalProperties": false,
  "properties": {
    "host_credentials": { "enum": ["none", "scoped"] },
    "network": {
      "type": "object", "additionalProperties": false,
      "properties": {
        "setup":        { "enum": ["on", "off"] },
        "verification": { "enum": ["on", "off"] }
      }
    },
    "artifacts": { "enum": ["allowlist", "all"] }
  }
}
```
**Coherent** policy ⟺ `host_credentials=="none"` ∧ `network.verification=="off"` ∧ `artifacts=="allowlist"` (`network.setup` may be on).

**Rules (in `_semantic`):**
```
will_run = (autonomy.requested in {L1,L2,L3}) or bool(trigger.type) or trigger.unattended
if execution.untrusted is True and not coherent(execution.policy):
    msg = "untrusted code needs a coherent isolation policy (host_credentials='none', "
          "network.verification='off', artifacts='allowlist'); super-looper doesn't run it — "
          "declare where it runs safely and hand the spec to your own isolated runner."
    (errors if will_run else warnings).append(msg)

# Inferential nudge (advisory, conservative — dependency-install / external-clone signals only,
# NOT merely 'runs tests', to avoid flagging trusted in-repo suites):
if execution.untrusted is not True and _looks_untrusted(spec):
    warnings.append("this loop appears to install/run third-party code; set execution.untrusted "
                    "and declare an isolation policy if so.")
```

**Builtin-checker parity (closes the 1.2 gap for the new object):** extend `_builtin_structural` to reject unknown keys under `execution.policy` and `execution.policy.network`, mirroring jsonschema — so the zero-dep path stays as strict as the rich one.

**Schema anti-drift:** add `test_schemas_in_sync` asserting the two schema files are byte-identical. (Full single-sourcing — generate one copy, and have `build_spec` call `max_autonomy` instead of re-deriving the ladder — remains an optional later cleanup.)

**TDD gates:** `test_untrusted_runs_without_policy_errors` (will_run) · `test_untrusted_l0_without_policy_warns_only` · `test_untrusted_network_on_verification_errors` · `test_untrusted_with_coherent_policy_validates` · `test_trusted_loop_needs_no_policy` (nightly-export still clean/L3) · `test_looks_untrusted_nudge_warns` · `test_builtin_rejects_unknown_policy_key` · `test_schemas_in_sync`.

**Risk:** low. Additive; regression surface is the two-schema edit (covered).

---

## 2.3 — Shadow verifiers → *sketches*, never proof ✅ DONE  *(honesty fix · folded in #6 static half · TDD)*

**Goal:** a "shadow" result is a **verifier sketch / discovery artifact** — "this proposed gate appears viable," never "upstream verified."

**Files:** `src/super_looper/case_study.py`, `src/super_looper/cli.py`, `references/state-and-verification.md`, `scripts/test_case_study.py`.

**Changes:**
- Rename `shadow*` → `sketch*`; CLI `case-study simulate-verifier` → `case-study sketch-verifier` (alias the old verb one release). Report language → "verifier sketch — proposed gate appears viable; NOT upstream-verified."
- A sketch yields `evidence_level:"sketch"`, **structurally barred** from `ready_for_pr_claim`/`confirmed_local` (make the guard explicit + tested).
- **#6 (static half only):** a declared verifier command with **no path token** no longer counts as `confirmed_local` — it's `unconfirmed` (a path-less command isn't proof a gate exists). *The "0 tests collected" case is a **runtime** check (`pytest --collect-only`) and is tagged as a separate follow-up, not part of 2.3.*
- Drop the single-hardcoded-template "framework"; keep the concept inline as a labeled example.

**TDD gates:** `test_sketch_pass_never_reaches_ready_claim` · `test_pathless_verifier_command_is_unconfirmed` (static #6) · `test_sketch_verifier_alias_still_works`.

**Risk:** medium — report semantics; mitigated by the structural-bar test.

---

## 2.4 — Extract the deterministic loop *driver* (core); quarantine the rest  *(after 2.3 · folds in #7 · reverses red-team adj. #4)*

**Goal:** the loop's deterministic control flow is the unique primitive — pull it out of the case-study harness (and out of any prompt) into a tiny **core** driver. The one place Phase 2 *adds* to the center; it's what "make the loop first-class" means.

**New core module — `src/super_looper/runtime.py`:**
```
run_loop(spec, *, propose, verify, store, clock=...) -> RunResult
```
- **Pure deterministic control flow — no LLM, network, or subprocess of its own.** Everything non-deterministic is *injected*:
  - `propose(context) -> change` — the model step (the **only** creative call).
  - `verify(change) -> VerifyResult(passed: bool, signal: str)` — the gate (a tool, *outside* the model).
  - `store` — durable state on disk: `load()` / `checkpoint(state)`.
  - `clock` — injected so budget/runtime is testable.
- Enforces **in code**, from the validated spec: `max_iterations`, `budget` (tokens/runtime/cost), `no_progress` (streak ≥ repeats).
- Applies the **keep/revert ratchet**, records each failure `signal`, **checkpoints state every iteration**.
- **#7 fold-in:** absent / partial / ambiguous evidence is treated as **failure** (fail-closed) — never "better" — so the ratchet can't keep unverified work.

**Reverses red-team adjustment #4:** the gate/evidence logic now *has* a core consumer (the driver's `verify` step), so it belongs in core after all.

**New CLI:** `super-looper run <spec> --propose <cmd> --verify <cmd>` drives the core loop — the model and the sandbox are *your* commands.

**Relegate to `experimental/`:** the repo-checkout / dependency-install / diff-packaging / maintainer-report plumbing from `case_study` (the "mini-CI" and "where it runs" parts) → `super_looper/experimental/case_study_harness.py`, which now **calls `runtime.run_loop`**. Drop the headroom-specific template (keep one labeled example). Heavy case-study verbs move under `super-looper experimental case-study …` (alias one release).

**TDD gates** (the driver is pure → fully testable with fakes, no live deps):
- `test_driver_stops_at_max_iterations` · `test_driver_stops_at_budget` · `test_driver_stops_on_no_progress_streak`
- `test_driver_keeps_on_pass_reverts_on_fail` (the ratchet)
- `test_driver_checkpoints_state_each_iteration`
- `test_driver_takes_deterministic_decisions_without_the_model` (stop/budget/state decided in code; `propose` called only for the change)
- `test_absent_evidence_is_failure_not_better` (#7, fail-closed)
- `test_experimental_harness_delegates_to_run_loop`

**Risk:** medium — new core code, but pure and deterministic; fully unit-testable with injected fakes.

---

## 2.5 — Repo audit becomes a *qualifying adapter*  *(was 2.5 + 2.6, merged · same module · folds in #9)*

**Goal:** identity = summonable intake that *feeds the core*; the core, not static evidence, decides what becomes a loop.

**Files:** `src/super_looper/repo_audit.py` (+ promote path), reports, `scripts/test_repo_audit.py`.

**Changes:**
- **Language:** "candidate loop" / "loop hypotheses" → **"automation lead"**. Output `loop-hypotheses.json` → `automation-leads.json`, **also writing the old filename as an alias** (deprecation note) for one release. Report prose changes freely (no alias needed — it's prose). `super-looper repo audit` stays. Output states "a lead is intake — it becomes a loop only by passing qualification."
- **Promotion requires qualification (was 2.6):** `repo promote <lead> [--answers human.json]` builds answers = **lead-derived ⊕ human-supplied**, runs `classify_answers`/`max_autonomy`, and emits `design/loop.json` **only** on `AUTONOMOUS_LOOP`; otherwise a **discovery packet**. Static repo evidence alone never grants a loop. *(The `--answers` supplement is essential — a static lead rarely knows budget/scope/finished_state, so without it promotion would always return discovery and be dead.)*
- **#9:** script/target-name matching uses **word boundaries**, not substring (`latest`⊅`test`). *(Deeper "derive category from the command body" stays F4.)* Re-check existing `test_repo_audit` fixtures, since word-boundary matching may drop a previously-matched gate.

**TDD gates:** `test_audit_emits_leads_not_loops` · `test_audit_legacy_filename_alias_written` · `test_promote_unqualified_lead_yields_discovery_packet` · `test_promote_with_answers_qualifies_to_loop` · `test_script_name_match_is_word_boundary` (#9).

**Risk:** low–medium — naming/output + promotion re-route; de-risked by the alias and the two promotion-branch tests.

---

## 2.2 — Quarantine the runner transport  *(last · folds in lazy CLI imports; closes #12/#13 by relegation)*

**Goal:** stop presenting bespoke SSH/container orchestration as the product.

**Changes:**
- Move `remote_runner.py` → `super_looper/experimental/remote_runner.py`; `runner` CLI verbs → `super-looper experimental runner …` with a deprecation note pointing to `execution.policy` (§2.1) and `SCOPE.md`.
- Strip the **asserted-but-unenforced** controls (#12 unconditional "network disabled"; #13 metadata-only allowlist) from the emitted plan — once experimental and not a guarantee, the honest move is to not assert controls it doesn't enforce.
- **Lazy CLI imports:** each subcommand imports its module inside the handler, so the `super-looper validate`/`explain`/`max-autonomy` paths no longer load the SSH planner or the audit engine.
- Keep the relocated tests.

**TDD gates:** `test_cli_validate_does_not_import_experimental` (run `cli.main(["validate", …])`, assert `remote_runner`/`repo_audit` absent from `sys.modules`) · `test_experimental_runner_still_plannable` · `test_runner_plan_has_no_unenforced_security_claims`.

**Risk:** medium — import-path move; pinned by the `sys.modules` test.

---

## Sequencing
`2.1 (+schema-sync)` → `2.3 (+#6 static)` → `2.4 (driver + #7 + quarantine)` → `2.5 (adapter + promotion + #9)` → `2.2 (+lazy imports)`
Lessons become a core primitive or a spec requirement (2.1, 2.3, 2.4-driver) before any module is relegated (2.4-move, 2.2).

## Close-out (after the five)
- **Release/version hygiene:** bump to `0.6.0`, sync `pyproject`/`__init__`, backfill the `v0.4.0` tag, add a fail-on-dirty-at-release check.
- **README/SKILL re-lead:** refusal-first message and the lean core first; the (now experimental) subsystems below; fix "six-question interview" → twelve.
- **Migration note** for renamed audit outputs and CLI verbs (aliases + when they drop).

## Definition of done (Phase 2)
1. An untrusted loop that will run without a coherent isolation policy is refused; a trusted loop and L0 drafts are unaffected (2.1).
2. No sketch result can reach a "ready/confirmed" claim, and a path-less verifier is `unconfirmed` (2.3, #6).
3. The **core driver** runs a validated loop's skeleton *in code* — caps · state-on-disk · keep/revert ratchet — calling the model only for the propose step, with absent evidence failing closed; the experimental harness delegates to it (2.4, #7).
4. Promotion emits a loop only on a real qualification verdict (2.5).
5. The audit speaks "automation lead", summonable, never minting a loop (2.5).
6. `super-looper validate` imports neither the runner nor the audit engine; runner/case-study live under `experimental/` (2.2).
7. Shipped as a tagged `0.6.0`, README led by the refusal-first core.
