# super-looper — Scope & North Star

**Date:** 2026-06-21 · **Companions:** [`REVIEW-2026-06-21.md`](./REVIEW-2026-06-21.md) · [`IMPROVEMENT-TODO.md`](./IMPROVEMENT-TODO.md)

---

## North star

> **Super Looper makes the loop a first-class *deterministic* object — define it, run its skeleton in code, bound it, persist its state — and decides whether a loop is justified and what autonomy it has earned.**
>
> **Determinism → code. Judgment → the model. Infrastructure → the environment.**

Most of a loop is *deterministic*: counting iterations, enforcing a budget, checkpointing state, invoking the gate, keeping-or-reverting. Faking those with prompt engineering is the core mistake — it is **unreliable** (LLMs are bad at deterministic bookkeeping) and **expensive** (you pay tokens to fake a `while` loop). Super Looper pulls that skeleton **out of the prompt and into code**, hands only the one genuinely creative step — *propose the next change* — to the model, leaves *where it runs* to your environment, and **refuses the loops that shouldn't exist at all.**

So there are **two** unique jobs, not one:

1. **Make "loop" first-class** — a validated loop *definition*, a deterministic *driver* that runs the skeleton, real *boundaries* (scope fence, stop conditions), and *state* on disk. The thing you otherwise fake with prompt engineering.
2. **Judge the loop** — the verdict (loop / not-a-loop / use-scheduler / discovery-required) and the earned autonomy ceiling, *before* anything runs.

We learned the judgment half the expensive way: a gate that wasn't a real end-to-end check was treated as evidence and the loop shipped wrong work (the smolagents trial). **A gate alone is not a loop.** Now a design requirement, not a footnote.

---

## The decision rule (how we classify every feature)

**First, the layer test** — every capability belongs to exactly one layer:

- **Deterministic control of the loop** (definition · execution skeleton · boundaries · state · the gate-as-tool · the validator) → **code we own — the core.**
- **Genuine judgment** (propose the next change; a verdict the validator can't compute) → **the model / the human, at call time** — never baked into code, never faked in a prompt either.
- **Where and how it runs** (sandbox · VPS · CI · logging · auth · deploy) → **the environment** — emit policy, don't own infra.
- **Opinions about *what* loops do** (domain templates · specific agent frameworks) → **a separate product.**

**Then the uniqueness refinement** for anything that passes the layer test as "core":

1. **Unique** — is this specific to making/judging loops, or does it exist anywhere else?
2. **Improves the core** — does it make the loop primitive more real (definition / execution / boundaries / state) or sharpen the judgment (verdict / ceiling), or just help *operate* a loop?

| Unique? | Improves core? | Disposition |
|---|---|---|
| ✅ | ✅ | **Core** — own it, make it excellent |
| ❌ | ✅ | **Don't build the capability — own the thinnest *adapter* that lets the core drive infra you already have** |
| ✅ | ❌ | **Adapter / separate concern** — it's a different job that *feeds* the core |
| ❌ | ❌ | **Discard** |

The refinement (the part a naive 2×2 gets wrong): a non-unique capability that improves value is **not discarded** — it becomes a **thin adapter**. The danger is owning the capability; the win is owning the *seam*. The VPS runner is the textbook case: don't build the sandbox, **emit the policy** and let your sandbox enforce it.

---

## The map

### Core — keep small and excellent (~1k LOC + a tiny driver)

*Make the loop first-class (the deterministic primitive):*
- **Loop-spec schema + zero-dependency validator + semantic lints** — the loop *definition* and *boundaries* as a first-class, enforceable object. (`validate.py`, `schemas/`) ✅ built
- **Loop driver** *(new in Phase 2.4 — the one place we add to the center)* — a tiny, framework-agnostic deterministic executor: reads a validated spec and runs the *skeleton* (budget / iteration / no-progress caps · state-on-disk · gate invocation · keep/revert ratchet), with the model's *propose* step and the sandbox **injected**. Makes a loop *runnable*, not merely described — execution + state pulled out of the prompt. (`runtime.py`)
- **State on disk** — durable progress out of the context window, managed by the driver, never accumulated in tokens.

*Judge the loop (the refusal + the ceiling):*
- **Verdict engine** — `NOT_A_LOOP` / `USE_SCHEDULER` / `HUMAN_IN_LOOP` / `DISCOVERY_REQUIRED` / `AUTONOMOUS_LOOP` / `REJECT_DESIGN`. (`design.py`)
- **`max_autonomy()` — the earned-autonomy ceiling.** The crown jewel. Mechanically refuses over-reach. (`validate.py`)
- **`DISCOVERY_REQUIRED`** — "I don't know" is L0 evidence-gathering, never permission to guess. (`design.py`)
- **The self-eval** — the skill's own regression gate (must actually invoke the skill). (`evals/`)
- **SKILL.md + references** — the prose that teaches the discipline.

### Adapters (summonable, feed the core — present but not the center)
- **Repo Discovery Adapter** (today's `repo_audit`). Scans a repo and emits **automation leads** — *not* "candidate loops." A lead is intake; it becomes a loop only by passing **core qualification**. Stays in the package; its identity is "intake," not "product center." **Renamed in language, summoned by command, never auto-promoting.**

### Policy, not infrastructure (emit requirements; let existing infra enforce them)
- **Execution policy** (the useful core extracted from `remote_runner`). A loop that wants unattended autonomy must carry, in its spec, a machine-checkable policy:
  > *isolated execution · no host credentials · no network during verification · artifact allowlisting.*
  super-looper **validates that the policy is present and coherent**, and refuses L2+/L3 without it. It does **not** SSH anywhere, provision VMs, or orchestrate containers. The user's devcontainer / VPS / CI / gVisor enforces it.

### Evidence discipline (a stance, not a runner)
- **The evidence ladder + "shadow = sketch, not proof."** A *shadow verifier* is a **verifier sketch / discovery artifact** — it shows a gate *might* be viable. It is **never** evidence that upstream is verified, and must never be able to reach a "ready" claim. This is core honesty, expressed as spec requirements and report language — not as a bespoke mini-CI.

### Quarantine (don't delete yet — extract the lesson, then deprecate)
- **`remote_runner` transport** (SSH/container/provider plumbing) and the **repo-specific / diff-packaging / mini-CI parts of `case_study`**. Mark `experimental`/deprecated. First extract the genuinely-useful core: the execution *policy* (above) and the deterministic loop *skeleton* (→ the core **driver**). Quarantine only what's left — *where* it runs and *how* it packages a repo's diff. Losing a lesson before it's a clean spec requirement or a core primitive is the real risk.

### Discard
- **Shadow-verifier *templates* as a code abstraction** (one hardcoded template masquerading as a framework). Keep the *concept* (a sketch) in policy/language; drop the machinery.

---

## What super-looper becomes

A lean center (~1k LOC + a tiny driver + `SKILL.md`) that does the two things nothing else does — **make the loop a runnable deterministic object** *and* **judge whether it should exist and how unattended it's earned** — surrounded by *summonable* adapters that feed it (discovery) or that it emits for someone else to enforce (execution policy). The perimeter stops expanding; the center gets sharper and honest:

- the validator enforces what the prose promises (gate quality caps the ceiling; typo'd caps rejected; no fabricated attestations);
- the project passes its own gate (CI invokes the skill, runs every test);
- "minimal loops" is true again at first contact.

**Non-goals (write them down so we stop drifting):** super-looper is **not** a sandbox/VM orchestrator, **not** a CI/test runner, **not** an auto-loop-generator from static scans, **not** a provider integration (DigitalOcean/AWS/SSH), and **not** an agent framework. The loop driver is a deterministic *skeleton* — a bounded `while`-loop with bookkeeping — that **injects** the model's propose-step and the sandbox; it does not implement them. When a task needs one of those, super-looper *names the requirement* and hands off.

---

## What a run looks like

### 1. The common case — getting talked out of a loop
```
$ super-looper interview --answers task.json     # or: describe the task; 12 questions
```
```jsonc
{ "verdict": "USE_SCHEDULER",
  "autonomy": "L0",
  "rationale": ["A fixed script plus the gate would do the job without model judgment."],
  "alternative": "Use cron/Task Scheduler/CI around the deterministic script." }
```
Most tasks end here — `NOT_A_LOOP`, `USE_SCHEDULER`, or `DISCOVERY_REQUIRED`, each with the reason and the cheaper path. That *is* the value.

### 2. A task that qualifies — a spec with an honest ceiling
```
$ super-looper validate my-loop.json --strict
$ super-looper max-autonomy my-loop.json --json
```
```jsonc
{ "earned": "L1",
  "missing_for_L2": ["a budget cap (stop_conditions.budget)", "a blast-radius fence (scope.must_not_touch)"],
  "missing_for_L3": ["an end-to-end tool gate on the real deliverable", "a proven manual pass"] }
```
It certifies **only** what's earned, and names exactly what unlocks more. A weasel gate (`"the report looks good"`) is **capped at L1** no matter what level you request — the smolagents lesson, enforced.

### 3. The repo-discovery adapter — summoned, never auto-promoting
```
$ super-looper repo audit --repo-path ../some-repo
```
Emits **automation leads** with repo-native gates inventoried and a ranked backlog. No lead is a loop. To become one it runs through **core qualification** (the same verdict engine): static repo evidence alone never grants autonomy. `repo promote <lead>` requires the lead to *pass qualification first*, not just to have a CI file.

### 4. Running untrusted code — policy emitted, your infra enforces
A loop that runs third-party code declares it, plus an isolation policy:
```jsonc
"execution": { "untrusted": true,
  "policy": { "host_credentials": "none", "network": { "setup": "on", "verification": "off" }, "artifacts": "allowlist" } }
```
super-looper validates the policy is coherent and **refuses to run it without one** — then hands the spec to *your* VPS / devcontainer / CI to execute. super-looper never logs into the box. You get "run the full suite somewhere disposable, with no fear for the main machine" because the loop *can't run untrusted without that policy* — not because super-looper became orchestration software.

### 5. The loop runs — driver in code, model only proposes
```
$ super-looper run my-loop.json --propose <your-model-cmd> --verify <your-gate-cmd>
```
The driver loads durable state from disk, then loops in **code**: check the budget / iteration / no-progress caps → ask your model for *one* change → run the gate (a tool, outside the model) → **keep** it if the gate passes, **revert** if not → checkpoint state → repeat until the gate is satisfied or a cap trips. The model is called once per iteration, for the single creative step; counting, budgeting, state, stop, and the ratchet are deterministic and spend no tokens. That is the loop, pulled out of the prompt.

---

*The core stays small and trustworthy — definition, driver, boundaries, state, and the refusal. The adapters are summoned and labeled. The perimeter is policy we emit, not infrastructure we own.*
