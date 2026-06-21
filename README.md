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
| `schemas/` + `scripts/` | JSON spec schema + compatibility wrappers + 68 tests |
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

**Audit a repo for automation candidates, not auto-generated loops:**
```
super-looper repo audit --repo-path ../some-repo --out repo-audit
```
The audit writes `repo-audit.json`, `gate-inventory.json`, `repo-surfaces.json`, `automation-candidates.json`, `loop-hypotheses.json`, `ranked-backlog.md`, and `recommendations.md`. It inventories repo-native gates from CI workflows, `pyproject.toml`, `package.json`, Makefile, tox/nox, Rust, and Go metadata, maps gates to bounded repo surfaces such as workflows, test suites, docs/examples, and code-quality paths, then classifies candidates as `plain_scheduler`, `human_in_loop`, `l2_candidate`, `discovery_required`, or `do_not_automate`. It also proposes clearly labeled loop hypotheses for plausible opportunities such as flaky CI triage, example smoke tests, integration drift, CLI contracts, release smoke checks, and performance watchpoints. Static audit never grants L3; it is discovery input for deciding whether autonomy is justified.

**Run a real-repo case study:**
```
super-looper case-study init --repo https://github.com/chopratejas/headroom --issue https://github.com/chopratejas/headroom/issues/1233 --out case-studies/headroom-ast-compression
super-looper case-study design case-studies/headroom-ast-compression
super-looper case-study resolve-verifier case-studies/headroom-ast-compression --repo-path ../headroom
super-looper case-study run case-studies/headroom-ast-compression --repo-path ../headroom --strict
super-looper case-study simulate-verifier case-studies/headroom-ast-compression --repo-path ../headroom --template python-ast-corpus
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for maintainer
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for pr
```
Case-study runs write `repo.json`, `loop.json`, `verifier-results.json`, `scope-check.json`, `diff.patch`, `summary.json`, and maintainer/PR markdown reports. The runner does not push or open PRs; it packages evidence so a human can decide whether to share a report or ship a patch.

`resolve-verifier` is the normal integrated path: it runs the confirmed repo-local verifier when it exists; if the declared verifier is missing, it falls back to a **shadow verifier** by default. Use `--no-shadow` to disable that fallback and produce a missing-gate report instead. A passing shadow verifier means "this proposed gate appears viable," not "upstream is verified."

**Prepare a secure remote VM runner before installing repo dependencies:**
```
super-looper runner keygen --name headroom-sandbox --out-dir .super-looper/runners

super-looper runner bootstrap-plan \
  --provider digitalocean \
  --ip 203.0.113.10 \
  --admin-identity-file ~/.ssh/do_bootstrap_key \
  --runner-public-key .super-looper/runners/headroom-sandbox_ed25519.pub \
  --runner-identity-file .super-looper/runners/headroom-sandbox_ed25519 \
  --profile-out .super-looper/runners/headroom-sandbox.profile.json \
  --out bootstrap-plan.json

super-looper runner plan \
  --profile .super-looper/runners/headroom-sandbox.profile.json \
  --case case-studies/headroom-ast-compression \
  --repo https://github.com/chopratejas/headroom \
  --setup deps \
  --allow-network-setup \
  --isolation container \
  --out remote-plan.json
```
Remote plans are local JSON only: they validate a hardened SSH/container policy without executing SSH. `bootstrap-plan` supports `digitalocean`, `aws`, `gcp`, `azure`, `hetzner`, and `custom` presets; the core runner is provider-neutral SSH. Defaults are credential-spillage resistant: dedicated runner key, no agent forwarding, no password auth, strict host-key checking, no host home/credential/package-cache mounts, verifier network disabled unless explicitly allowed, artifact allowlist only, and remote workdir cleanup by default. See [`references/remote-runners.md`](references/remote-runners.md).

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
