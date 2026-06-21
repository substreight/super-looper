```
███████╗██╗   ██╗██████╗ ███████╗██████╗
██╔════╝██║   ██║██╔══██╗██╔════╝██╔══██╗
███████╗██║   ██║██████╔╝█████╗  ██████╔╝
╚════██║██║   ██║██╔═══╝ ██╔══╝  ██╔══██╗
███████║╚██████╔╝██║     ███████╗██║  ██║
╚══════╝ ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝
██╗      ██████╗  ██████╗ ██████╗ ███████╗██████╗
██║     ██╔═══██╗██╔═══██╗██╔══██╗██╔════╝██╔══██╗
██║     ██║   ██║██║   ██║██████╔╝█████╗  ██████╔╝
██║     ██║   ██║██║   ██║██╔═══╝ ██╔══╝  ██╔══██╗
███████╗╚██████╔╝╚██████╔╝██║     ███████╗██║  ██║
╚══════╝ ╚═════╝  ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═╝
```

> **A loop is a goal plus a gate. The gate is the design.**

**super-looper** is a meta-skill for designing clean, minimal **agentic loops** — and, more often, for talking you *out* of building one.

The unglamorous pitch: most "autonomous loop" ideas are net-negative — they spin, drift, or quietly bill you to ship confidently-wrong work *faster*. So super-looper's first job is to say **no**. Its second is to make the rare loop that *is* worth building actually converge — by forcing you to design the gate before the machinery, keep state out of the context window, and never let the thing being judged grade itself. It enforces the non-negotiables with a machine-checkable spec + a **zero-dependency validator**, and ships with **its own eval suite** so the skill can't silently regress.

It insists on two more things. Autonomy is **earned, not toggled** — a loop runs only as unattended as its gate, scope, budget, reversibility, and proven manual pass allow, and the validator refuses anything more. And you shouldn't have to read the skill to use it: a six-question interview derives the verdict and the spec, `DISCOVERY_REQUIRED` handles unknown answers without guessing, and `--explain` previews any loop in one plain sentence.

## The one idea
An agentic loop runs DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE on its own, until an objective gate passes or a hard limit trips — no human pushing each step. The part that makes it a loop and not a model talking to itself is **VERIFY**: a check, ideally outside the model, that can actually *fail* the work.

So you design the **verifier first**. If you can't write a gate that fails bad work automatically — and that gates the *deliverable*, not just the plumbing — it isn't a loop yet. Most tasks aren't.

## What's in the box
| path | what |
|---|---|
| `SKILL.md` | the skill — load it into your agent harness |
| `references/` | 5 filled templates · state architecture · failure modes · **verified** evidence |
| `src/super_looper/` | installable CLI + importable validator/compiler package |
| `schemas/` + `scripts/` | JSON spec schema + compatibility wrappers + 49 tests |
| `examples/` | worked loop specs + interview answer fixtures, including a Headroom case study |
| `case-studies/` | public-target manifests and reports that show what autonomy level a real task actually earns |
| `evals/` | the skill's own gate — labeled scenarios + a deterministic scorer (10/10 baseline) |

## Quickstart
**Design a loop (or get talked out of one):** point your agent at `SKILL.md`. It qualifies via Step 0, designs the gate first, ranks the options, and hands *you* the decision. Haven't read the skill? Just describe your task — it runs a six-question interview (does it recur? what would automatically prove a result wrong? what must it never touch?) and derives the rest.

**Install the CLI:**
```
python -m pip install .
super-looper --version
```

**Compile interview answers:**
```
super-looper questions
super-looper interview --answers examples/unknown-gate.answers.json
super-looper interview --answers examples/ts-client.answers.json --out draft.loop.json
```
If the human can't answer a critical question, the compiler returns `DISCOVERY_REQUIRED` and an L0 discovery plan instead of inventing a loop.

**Validate & preview a spec:**
```
super-looper validate my-loop.json --strict
super-looper render my-loop.json
super-looper explain my-loop.json
super-looper max-autonomy my-loop.json --json
```
Zero deps — uses `jsonschema` if installed or via `pip install .[jsonschema]`, otherwise falls back to a built-in checker. The old `python scripts/*.py` commands remain as compatibility wrappers.

**Run a real-repo case study:**
```
super-looper case-study init --repo https://github.com/chopratejas/headroom --issue https://github.com/chopratejas/headroom/issues/1233 --out case-studies/headroom-ast-compression
super-looper case-study design case-studies/headroom-ast-compression
super-looper case-study run case-studies/headroom-ast-compression --repo-path ../headroom --strict
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for maintainer
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for pr
```
Case-study runs write `repo.json`, `loop.json`, `verifier-results.json`, `scope-check.json`, `diff.patch`, `summary.json`, and maintainer/PR markdown reports. The runner does not push or open PRs; it packages evidence so a human can decide whether to share a report or ship a patch.

**Gate the skill itself** (run after any edit to it):
```
cd evals && python score_eval.py scenarios.jsonl results.example.jsonl --min 0.8   # -> 10/10
```

## The five-part anatomy
- **Goal** — a contract, not a prompt: end state · evidence · constraints · budget.
- **Verifier** — the gate, ranked by trust: tool > independent model > human. Self-grading is *off* the ladder.
- **State** — on disk, not accumulating in the context. Clean-ish context per unit of work.
- **Stop conditions** — success · a hard cap (iterations **and** budget) · no-progress detection. All three.
- **Maker ≠ checker** — don't let the agent that did the work be its own only gate.

## Autonomy is earned, not toggled
A loop runs only as unattended as it has *earned*. The validator computes the ceiling and refuses anything above it, naming what's missing:

- **L0 · advise** — designs and previews, runs nothing
- **L1 · propose & confirm** — does the work, stops at each decision point
- **L2 · act with guardrails** — real automatic gate + scope fence + machine budget cap
- **L3 · unattended** — trigger, no human, reports after — *only* with a rung-1 end-to-end gate on the deliverable, scope fence, budget cap, reversible output, and `autonomy.proven_manual_pass: true`

## Why trust any of this
The load-bearing claims are sourced in [`references/evidence.md`](references/evidence.md): self-correction limits (Huang 2024), self-preference bias (Panickssery 2024), context rot (Liu/TACL 2024; Chroma & NoLiMa 2025), and verifiable rewards (Tulu 3; DeepSeek-R1). The named techniques ("Ralph," evaluator-optimizer, harnesses) are mostly blog-evidenced — so design from the principles, not the hype.

## License
MIT — see [`LICENSE`](LICENSE).
