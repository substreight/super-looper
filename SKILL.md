---
name: loop-design
description: Design clean, minimal agentic loops — and decide whether a loop is even warranted. Use this whenever someone wants to automate a recurring task with an AI agent, audit a repository for automation candidates, build a self-iterating or self-checking agent, set up a scheduled or event-triggered AI job, turn a manual prompt into something that runs itself, or asks about "loops," "agentic loops," the "Ralph" technique, harnesses, verifier/gate design, maker-checker or evaluator-optimizer setups, or why their autonomous agent spins, drifts, exits early, or burns tokens. Also use when the right answer is to NOT build a loop and use a single prompt or interactive session instead — qualifying that is a core job of this skill.
---

# Loop Design

A meta-skill for designing agentic loops: an agent that pursues a goal, checks its result against an objective gate, and iterates until it passes or hits a hard limit — with no human pushing each step.

This skill teaches the *principle*, not any one branded technique. "Ralph," evaluator-optimizer, and the various harnesses are named implementations of the same small set of ideas below. There is no settled industry best practice here yet — the vocabulary is barely a year old and most of it is evidenced by blog posts, not controlled evaluation. Design from the principles; treat the named techniques as options with tradeoffs.

## The one idea this skill exists to enforce

**A loop is a goal plus a gate. The gate is the design.**

A prompt produces one answer and waits. A loop runs DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE on its own. The part that makes it a loop rather than a model talking to itself is VERIFY: a check, ideally outside the model, that can actually fail the work. Without a real gate, iteration is not progress — a fast loop with no gate just produces wrong answers faster, and bills you each round to do it.

So the design order that produces clean loops is counterintuitive: **design the verifier before the loop body.** Most people write the agent first and bolt a check on at the end. Gate-first forces "done" to become objective before any machinery exists. If you cannot write a gate that fails bad work automatically, stop — the task is not a loop yet.

## Step 0 — Qualify. Should this even be a loop?

The most important step, and the one people skip. The honest default is **no — use one good prompt or an interactive session.** For most tasks an interactive session with a capable agent is faster and safer than engineering a loop. Loops have real setup and token cost; most tasks don't earn it.

Recommend a loop **only if all of these hold**:

1. **It recurs** — at least roughly weekly. A one-off never repays the setup.
2. **Bad output can be rejected automatically** — a test, type check, build, lint, schema, threshold, or hard rule can fail it without a human. If nothing can fail it, the loop just spins. **The check must reject a bad version of the thing you actually want — not merely confirm the action happened.** "The email sent," "the comment posted," "the file wrote," "HTTP 200" are *delivery guards*, not verifiers. If the only objective check is on plumbing while the valuable output stays subjective, it's a scheduled draft-generator, not an autonomous loop.
3. **The agent can do the whole task end-to-end** — not hand half back each round.
4. **"Done" is objective** — not a matter of taste. If quality is a judgment call, a human still wins the verify step, so it isn't an autonomous loop.
5. **The economics work** — you're on prepaid/flat-rate capacity where inference is effectively sunk cost, *or* you've already shown the loop is cheap per accepted result. On metered API pricing, an unproven autonomous loop is usually the wrong tool — overnight loops have produced five-figure daily bills fixing trivial things.

**A time trigger is not, by itself, a reason to build an agent loop.** "Run X every night" is scheduling, not a loop. If each run's work is deterministic — run a script, validate the output, no judgment — put the *schedule* in cron (Linux/macOS) or Task Scheduler (Windows) and skip the agent entirely. **Decision test:** strip the LLM and run a fixed script plus the gate — would the job still do what's asked? If yes, it's a scheduled task; the LLM belongs inside only if its judgment changes the output or repairs a non-deterministic failure the script can't. And needing an LLM only qualifies it to be *in* the job — it does **not** make the job an autonomous loop. If the judgment-laden output is the part nothing can objectively fail (the prose, the "best" pick, the summary quality), the human is still the real gate: that's a scheduled draft-generator or human-in-the-loop, **never** an autonomous loop. (A scheduled job can still be a legitimate loop — see the nightly-export example — but because its gate catches a non-deterministic failure in the actual deliverable, not because it runs on a timer.)

Miss one → say so plainly and recommend the alternative: a one-shot prompt, an interactive session, a human-in-the-loop workflow, or — when it's deterministic work on a timer — a plain scheduled job (cron / Task Scheduler), no agent. Talking someone out of an unnecessary loop is a successful use of this skill, not a failure. Don't build machinery to look helpful.

**Qualify by interview, not lecture.** If the person hasn't read this skill, don't make them — ask six questions and derive the rest:

1. **Does it recur, and how often?** (weekly+ to earn the setup)
2. **What would automatically prove a result is *wrong*?** — the gate, in their words. *If the honest answer is "a human would just know," it isn't a loop yet; stop here.*
3. **What's the finished state, and what evidence shows you reached it?** (end_state + evidence)
4. **What must it never touch, and does its output post / ship / delete anything?** (scope fence + reversibility)
5. **Attended or unattended — and on prepaid or metered capacity?** (sets the autonomy ceiling and the budget bar)
6. **Most you'll spend per run, and per accepted result?** (the budget cap and the economic test)

Question 2 decides everything: if nothing can fail the work automatically, route them to a one-shot, a scheduled job, or a human-gated draft — don't build a loop.

**If the human literally cannot answer, do not guess.** Return `DISCOVERY_REQUIRED` and keep autonomy at **L0**. Unknown answers are evidence-gathering work, not missing form fields. Give a short discovery plan: run one watched manual attempt, capture one bad output, name the smallest check that would reject it, define `may_touch` / `must_not_touch`, and set a machine-readable budget cap. Only resume loop design after those facts exist. The deterministic helper is:

```
super-looper questions
super-looper interview --answers examples/unknown-gate.answers.json
super-looper interview --answers examples/ts-client.answers.json --out draft.loop.json
```

**If the user points at a repository and asks what to automate, run discovery before design.** Use `super-looper repo audit --repo-path <repo> --out <audit-dir>` and treat the output as a ranked backlog: `plain_scheduler`, `human_in_loop`, `l2_candidate`, `discovery_required`, or `do_not_automate`. Prefer candidates with `surface_id` because they are tied to bounded repo surfaces such as a CI workflow, test suite, docs/examples surface, or code-quality path. Use `loop-hypotheses.json` for creative possibilities, but keep `hypothesis: true` ideas in discovery until their proposed verifier is proven. Do not turn every candidate into a loop. Static repo audit inventories gates and allocates ceilings; it never grants L3.

## The anatomy of a clean loop

Five parts. Name each one explicitly; a loop missing any of them fails in a predictable way (see `references/failure-modes.md`).

- **Goal** — read it as a *contract*, not a prompt: name the end state you want, the evidence that proves you reached it, the constraints it must not break getting there, and the budget it may spend. "All tests in `/auth` green, lint clean, zero type errors" — not "fix the auth code." Leave any of the four vague and the model fills the gap with the easiest reading: it stops early, takes a shortcut, or redefines success so the transcript looks done while the system is broken.
- **Verifier (the gate)** — the check that rejects bad work, ranked by trust on the verifier ladder below. This *is* the design.
- **State** — two distinct things live on disk, outside the model's context, not accumulating in the conversation. *Durable context*: the conventions, build steps, and project rules the agent re-reads every run (e.g. a `CLAUDE.md` / rules file) — skip it and the loop re-derives your project from scratch each pass and guesses the gaps. *Durable progress*: what's done, what failed, what's next (a plan file, `progress.txt`, a board). The model forgets between runs; the files don't. See "State architecture" below — this is the part most naive loops get wrong.
- **Stop conditions** — three exits: success, a hard cap (max iterations *and* a token/cost budget), and **no-progress detection** (halt when the same error, an empty diff, or the same failing test recurs N times). A loop with only a success exit runs until it succeeds, breaks, or drains the account.
- **Maker ≠ checker** — separate the agent that does the work from the one that verifies it. Don't let the maker be its own only gate (see the ladder).

## The verifier ladder

Pick the highest rung the task allows. The gap between rungs is large.

1. **Tool / computational gate** — tests, build, type checker, linter, schema validation, a numeric threshold. The gate can't be argued with. Always prefer this; it's why code loops are the easiest to get right. The strongest version *exercises the real system end-to-end* rather than trusting a self-reported result: hit a live endpoint and check the response, drive the actual UI in a browser, run it in a simulator. For anything running unattended, this end-to-end check is the single thing that makes the autonomy safe — without it, four other safeguards still let confidently-wrong work through.
2. **Independent model critique** — a *different* model (at least as capable as the maker), given the artifact and the criteria but **not the maker's own justification for why it's done**. Withholding the maker's reasoning matters: a confident wrong rationale can persuade a judge into approving bad work, and models favor their own generations. Use a rubric and, for borderline cases, confidence-tiered routing (clear pass → accept; uncertain → log and flag for human; fail → block). For multimodal work, a vision model that checks a screenshot against the spec is a legitimate rung-2 checker.
3. **Human gate** — for irreducibly subjective "done." This is legitimate, but it means the loop is human-in-the-loop, not autonomous. Name that honestly.

**Off the ladder: the maker grading its own work.** Self-checking is not a weak gate, it can be a *negative* one — without external feedback, self-correction frequently leaves output the same or worse, and seeing its own draft can make the model *less* calibrated about whether it's correct. Use self-scoring only as a drafting aid (Template 2), never as the gate for anything the model can be confidently wrong about.

## State architecture — clean context per unit of work

The single biggest mistake in naive loops is letting context accumulate: by iteration ten you're re-sending ten copies of the goal plus every prior tool result, which is both expensive and *quality-degrading* — recall drops as the context grows ("context rot"). The fix is not "trim a bit." It's to keep durable state outside the model and give each unit of work a clean-ish context. Two attested patterns:

- **Fresh-context restart** — each iteration starts a new instance, reads minimal state from disk (plan, progress, last failure), does one item, writes state back, exits. Best when work decomposes into independent units (e.g. tasks in a plan file). The "Ralph" technique is the brute-force version of this; it works but is token-hungry and crude — use the disciplined form (one scoped item per pass, real gate, hard caps), not raw "re-run the same prompt until something passes."
- **Compaction** — keep one session but summarize and reinitialize when nearing the limit, merging new facts into a persisted summary rather than regenerating from scratch. Best when continuity matters and the work doesn't cleanly split.

Decision rule: if the task splits into independent items with a checkable result each, prefer fresh-context restart; if it's one continuous reasoning thread, prefer compaction. Either way, the plan and progress live in files. Detail and the decision in `references/state-and-verification.md`.

## Design workflow

Work these in order; don't move on with a gap.

1. **Qualify** (Step 0). If it fails, stop and recommend the alternative.
2. **State the goal as the gate's pass condition.** If you can't phrase it as objectively true/false, push back until you can, or downgrade to human-checked.
3. **Design the verifier first** — pick the highest ladder rung available. If the only check is "the same model thinks it's good," flag that the loop won't reliably converge.
4. **Choose the state architecture** — fresh-restart vs compaction (above). Decide what minimal state persists to disk.
5. **Set all three stop conditions** — success, hard cap (iterations + budget), no-progress detection. Decide on-stop behavior: summarize what changed and what's still open; never exit claiming a false "done."
6. **Decide the maker/checker split** — same agent or separate, which model on each. Justify the cost of a split.
7. **Write the spec** in the canonical form (see `references/loop-spec-templates.md`).
8. **Prove one manual pass before automating** (build order below).

## Output — the canonical loop spec

Produce the loop as a compact spec, not prose:

```
GOAL:        <objective pass condition>
SCOPE:       <what it may read/touch; what it must never touch>
EACH ITERATION (clean context):
  1. load state (plan / progress / last failure) from disk
  2. pick the single highest-impact open item
  3. make the smallest change; if retrying, CHANGE APPROACH, don't repeat the last
  4. run the verifier; write state back
VERIFY:      <gate — name the ladder rung>
STATE:       <on disk: done / failed / next>
STOP WHEN:   verify passes  OR  N iterations  OR  budget hit  OR  same failure ×K
ON STOP:     summarize changes + open gaps; never claim false done
REPORT:      <where the result/summary goes>
MAKER:       <model/effort>   CHECKER: <model/effort, if separate>
```

`references/loop-spec-templates.md` has filled templates: a rigorous code/CI loop, a portable "paste into any chat model" self-checking loop (no tooling, with its honest limits), lightweight scheduled/ops automation, and gate-hardening patterns. Read it before writing a spec.

## Machine-checkable spec (JSON) — keep both forms

The block above is the human-readable spec; produce it always. When the loop will be wired into a real harness, **also** emit a JSON spec conforming to `schemas/loop-spec.schema.json`, and validate it. The JSON is the source of truth — the human-readable form can be regenerated from it, so the two never drift.

The schema and validator exist to enforce this skill's non-negotiables mechanically, so a missing gate or budget fails *before* the loop runs rather than at 3am:

```
super-looper validate my-loop.json            # validate (exit 1 on error)
super-looper render my-loop.json              # print the human-readable spec
super-looper explain my-loop.json             # one-sentence plain-language preview
super-looper validate my-loop.json --strict   # treat warnings as errors
super-looper interview --answers answers.json --out my-loop.json
```

Structural rules (required fields, enums) live in the schema; the validator adds the judgment the schema can't express and will **error** on: a `self` verifier rung (maker grading itself is off the ladder), `state.on_disk: false` (context-accumulation anti-pattern), an unattended loop with no trustworthy gate, an unattended loop with no budget cap, L2 requested without both a budget cap and scope fence, L3 requested without an unattended trigger, end-to-end rung-1 tool gate, explicit reversible output, or `autonomy.proven_manual_pass: true`, parallelism > 1 with no isolation, and an `autonomy.requested` level higher than the loop has earned (it computes the ceiling via `max_autonomy(spec)` and names what's missing). It **warns** on a same-model checker, an unattended metered loop that isn't proven cheap, a missing budget cap on an attended loop, a gate phrased as a taste judgment or with no machine-decidable signal, a single-pass loop (`max_iterations: 1`) that never iterates and is likely a scheduled one-shot, and spec parts that don't refer to each other (evidence ↔ verifier, success ↔ end_state). The validator is dependency-free (uses the `jsonschema` library if installed, falls back to a built-in checker — a missing or misplaced schema file degrades to the built-in rather than crashing) and importable, so a harness can call `validate(spec)` before each run. A worked instance is in `examples/nightly-export.loop.json`.

When emitting JSON, fill the four `goal` parts (end_state, evidence, constraints, budget) deliberately — they are the contract, and the validator treats vague/empty ones as errors. One honest limit: the validator can flag a gate that's absent, self-graded, or phrased as taste — it **cannot** confirm that a gate which *exists* actually separates good output from bad. That's a property of how the gate behaves on real inputs, not of the spec text; only running the gate (or tracking accept-rate over real runs) closes that gap. Designing a discriminating gate stays your job.

## Human decision points — surface a clear choice where judgment is irreducible

A loop is autonomous *inside* its gate; the human's leverage is at the edges. Make these choices explicit; don't bury them or self-certify them:

1. **Qualify verdict** — on any borderline case (is "done" really objective? does it recur? are the economics ok?), confirm with the human before building. Don't quietly resolve a fuzzy Step 0 in favor of building.
2. **Proposal triage** — when you propose more than one loop, rank them *and hand the ranking back* for the human to confirm, re-rank, or interrogate before anything is built (see the output contract below).
3. **Gate approval** — the validator can prove a gate *exists*, never that it's *good*. The human signs off on the verifier, especially rungs 2–3.
4. **Scope + budget + economics** — before scheduling: the must-not-touch list, the budget cap, prepaid-vs-metered, attended-vs-unattended. The human owns the blast radius.
5. **Output review** — the manual first pass, then ongoing review of what the loop ships (the comprehension-debt gate). Loop count is bounded by human review throughput, not by what the agent can generate.

## Autonomy levels — earn the dial

Autonomy is not a switch the user flips; it's a dial whose **ceiling the loop has to earn.** A free "run it fully autonomously" toggle would bypass the one thing that makes autonomy safe — the gate. The human can always dial *down* (more involvement); they can only dial *up* if the loop's properties license it — and if they can't, **refuse and name what's missing.**

| Level | What it does | Earned when |
|---|---|---|
| **L0 · advise / dry-run** | designs it, previews the plan + cost + blast radius, runs nothing | always |
| **L1 · propose & confirm** | does the work, stops at each human decision point (above) | always |
| **L2 · act with guardrails** | runs end-to-end, pauses only at the non-negotiables (irreversible/outward action · budget breach · no-progress) | a real automatic gate (rung 1–2) + `scope.must_not_touch` + `stop_conditions.budget` |
| **L3 · unattended** | runs on a trigger, no human in the loop, reports after | rung-1 end-to-end tool gate on the deliverable + unattended trigger + `scope.must_not_touch` + `stop_conditions.budget` + `autonomy.output_reversibility: reversible` + `autonomy.proven_manual_pass: true` |

The ceiling is the **lowest** cap implied by these axes:
- **Gate rung** — `self`/none → L1 (can't run unsupervised without a real gate); `human` → L1 (a human gate *is* human-in-the-loop); `independent_model` → L2; `tool` → up to L3.
- **Budget** — no machine-enforced cap → max L1. A human-readable budget summary is not enough.
- **Scope** — no `must_not_touch` fence → max L1. Nothing bounds the blast radius.
- **Trigger** — no explicit unattended trigger → max L2. L3 means it actually runs without a human present.
- **End-to-end** — a tool gate that does not exercise the real deliverable → max L2 for unattended use.
- **Reversibility** — missing or outward-facing / irreversible output → max L2. A PR you review is reversible; a posted message or a prod write is not.
- **Proven** — no `autonomy.proven_manual_pass: true` after ≥1 watched run → max L2. This is separate from `economics.proven_cheap`; cheap is not proven.

This is why a rung-1, PR-emitting loop can go L3 while a "post a first reply to every issue" loop (fuzzy gate, outward-facing) can't. The validator computes this — `max_autonomy(spec)` — and **errors if `autonomy.requested` exceeds what's earned**, listing what to add. When a user asks for more autonomy than the loop has earned, don't argue — name the missing piece ("make the gate rung-1, or keep a human at the publish step, and L3 unlocks"). That refusal *is* the product.

## Proposing loops — the output contract

When you surface candidate loops, **every candidate gets the same structure** — even the ones you'll recommend against — so they're comparable and none is silently shortchanged. A thin proposal reads as "already decided," which steals the human's choice; **uniformity is not optional, brevity is fine.** Per candidate:

- **Verdict** — autonomous loop / discovery-required / scheduler / human-in-the-loop / not-a-loop / reject-design
- **Qualify (Step 0)** — the five checks + the gate-covers-the-deliverable test, each pass/fail
- **Gate** — the concrete check and its ladder rung
- **Shape & trigger** — completion vs cadence; what fires it
- **Spec sketch** — the compact GOAL / SCOPE / VERIFY / STOP form
- **Buys / costs** — the value, and the economics
- **Won't catch / risks** — the honest limits
- **Rank rationale + confidence**, and **the one open question** a human should answer

Then present the set **ranked on explicit criteria** (leverage · gate strength · effort · risk), and **stop for the human** to confirm, re-rank, **drop or add candidates (curate which are in scope at all)**, ask questions, or pick — never auto-proceed to building from your own ranking. The human curates *and* orders the set: inclusion is their call as much as order, and the ranking is a recommendation, not a decision.

**Preview in plain language.** Alongside the spec sketch, give a one-sentence, jargon-free preview a non-expert can sanity-check — what it runs, what it checks, when it stops, what it touches, whether the output is reversible, and the autonomy level it's earned. (`super-looper explain` renders exactly this from the JSON.) The spec is for you; the sentence is for the person deciding whether to run it.

**Refuse helpfully.** A "not a loop" or "can't earn that autonomy" verdict is never a bare no — always pair the *why* with the concrete alternative (a one-shot prompt · a scheduled job (cron/Task Scheduler) · a human-gated draft · a lower autonomy level) and what would unlock more. The job is to route the user to the right tool, not just to decline.

## Cost discipline

Loops bill per pass; a maker/checker split roughly doubles it. Treat cost as a design constraint:

- **Track cost per accepted change, not tokens or iterations.** If you discard most of what the loop produces, you're doing the review it was meant to save — the gate or the premise is broken. Below roughly a 50% accept rate, kill it or fix the gate.
- **Clean context per pass** (above) is the main lever; it stops the per-iteration cost from compounding.
- **Cheap model on routine steps, strong model only at the gate** where judgment matters.
- **Always set a budget stop**, not just an iteration cap. Prefer prepaid/flat-rate capacity for anything that runs unattended.

## The loop lives in a harness

A production loop isn't just the iteration — it sits in a harness: the trigger (cron, CI, event), the tool set (keep it small; 3–5 focused tools beat 50, which degrade tool selection), the scope constraints, the budget, and the observability that lets you see drift and spend. Design the harness, not just the prompt.

Two harness details that bite once you scale past one loop. **Isolation:** the moment more than one agent runs at once, each needs a private checkout — a git worktree or a disposable sandbox — or concurrent agents overwrite each other's files. Below that count it's optional; at that count it's mandatory. If a case study needs dependency installs, untrusted build scripts, browser downloads, model downloads, or full repo-native tests, treat it as a higher-risk runner tier and plan it in a disposable container/VM before touching the host. Prefer the `super-looper runner keygen` → `runner bootstrap-plan` → `runner plan --profile` flow in `references/remote-runners.md`; it keeps the runner provider-neutral while offering DigitalOcean/AWS/GCP/Azure/Hetzner/custom presets. **Loop shape:** a loop is either *completion-conditioned* (run turns until a checkable end state is true, e.g. Claude Code's `/goal`) or *cadence-driven* (re-run on a schedule for open-ended work with no single finish line, e.g. `/loop`, cron — the PR-babysitter shape). Pick deliberately; they have different stop logic.

## Build order — never skip ahead

Scheduling something you haven't proven by hand is how loops blow up while you sleep.

1. **Dry-run first (L0)** — produce the change / diff / PR *without applying it*, and read it. The cheapest way to see what the loop will actually do before it can do anything.
2. **Get one manual run reliable** — by hand, watching it apply. This is the *proven manual pass* that L3 (unattended) requires: no proven run, no unattended.
3. **Save it as a skill / reusable instruction** — rules, patterns, and a hard list of what it must never touch.
4. **Wrap it in a loop** — add the gate and the stop conditions.
5. **Raise the autonomy dial only as far as the loop has earned** (see *Autonomy levels*), then schedule or trigger it.

Prove it once, harden it, then automate. Recommend the lightweight portable loop (Template 2) before any hosted machinery — most everyday tasks never need the heavy version, and saying so is part of the job.

## Reference files

- `references/loop-spec-templates.md` — five canonical, filled-in loop specs to adapt (incl. the invariant→regression-test backfill and the gate-coverage strengthener). Read before writing a spec.
- `references/state-and-verification.md` — fresh-restart vs compaction decision, and the verifier ladder rationale with the evidence on why self-verification is unreliable. Read when choosing an architecture or designing a gate.
- `references/failure-modes.md` — the anti-patterns each missing part produces, how to detect them, and the fix. Read when diagnosing a loop that spins, drifts, exits early, or overspends.
- `references/evidence.md` — verified citations for the skill's load-bearing empirical claims (self-correction, self-preference, context rot, verifiable rewards).
- `references/repo-discovery.md` — conservative repository audit workflow for finding automation candidates, ranking them, and refusing bad loops before spec design.
- `references/remote-runners.md` — secure remote VM/container runner policy for case studies that install dependencies or run untrusted setup code. Read before planning a dependency-installing case-study run.
- `schemas/loop-spec.schema.json` — JSON Schema for a loop spec. The machine-checkable form of everything above.
- `src/super_looper/` — installable package and `super-looper` CLI. The `scripts/*.py` files are compatibility wrappers.
- `scripts/validate_loop_spec.py` — validates a JSON spec (structural + the skill's judgment rules) and renders the human-readable spec from it. Dependency-free; importable as `validate(spec)`.
- `scripts/test_validate_loop_spec.py` — tests for the validator (pytest, or standalone `python scripts/test_validate_loop_spec.py`).
- `examples/nightly-export.loop.json` — a worked, valid JSON spec.
- `evals/` — the skill's own gate: labeled scenarios + a deterministic scorer. Re-run after editing the skill (see `evals/EVAL.md`).
