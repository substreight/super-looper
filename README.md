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

## The one idea
An agentic loop runs DISCOVER → PLAN → EXECUTE → VERIFY → ITERATE on its own, until an objective gate passes or a hard limit trips — no human pushing each step. The part that makes it a loop and not a model talking to itself is **VERIFY**: a check, ideally outside the model, that can actually *fail* the work.

So you design the **verifier first**. If you can't write a gate that fails bad work automatically — and that gates the *deliverable*, not just the plumbing — it isn't a loop yet. Most tasks aren't.

## What's in the box
| path | what |
|---|---|
| `SKILL.md` | the skill — load it into your agent harness |
| `references/` | 5 filled templates · state architecture · failure modes · **verified** evidence |
| `schemas/` + `scripts/` | JSON spec schema + a dependency-free validator (`validate(spec) -> errors, warnings`) · 20 tests |
| `examples/` | a worked, valid loop spec |
| `evals/` | the skill's own gate — labeled scenarios + a deterministic scorer (8/8 baseline) |

## Quickstart
**Design a loop (or get talked out of one):** point your agent at `SKILL.md`. It qualifies via Step 0, designs the gate first, ranks the options, and hands *you* the decision.

**Validate a spec:**
```
python scripts/validate_loop_spec.py my-loop.json --render
```
Zero deps — uses `jsonschema` if installed, falls back to a built-in checker.

**Gate the skill itself** (run after any edit to it):
```
cd evals && python score_eval.py scenarios.jsonl results.example.jsonl --min 0.8   # -> 8/8
```

## The five-part anatomy
- **Goal** — a contract, not a prompt: end state · evidence · constraints · budget.
- **Verifier** — the gate, ranked by trust: tool > independent model > human. Self-grading is *off* the ladder.
- **State** — on disk, not accumulating in the context. Clean-ish context per unit of work.
- **Stop conditions** — success · a hard cap (iterations **and** budget) · no-progress detection. All three.
- **Maker ≠ checker** — don't let the agent that did the work be its own only gate.

## Why trust any of this
The load-bearing claims are sourced in [`references/evidence.md`](references/evidence.md): self-correction limits (Huang 2024), self-preference bias (Panickssery 2024), context rot (Liu/TACL 2024; Chroma & NoLiMa 2025), and verifiable rewards (Tulu 3; DeepSeek-R1). The named techniques ("Ralph," evaluator-optimizer, harnesses) are mostly blog-evidenced — so design from the principles, not the hype.

## License
MIT — see [`LICENSE`](LICENSE).
