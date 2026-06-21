# Repo Discovery

Use repo discovery when a user asks to point Super Looper at a repository and find useful automation opportunities.

## Positioning

Repo discovery is not loop generation. It is a conservative triage pass:

1. Inventory repo-native gates.
2. Map gates to bounded repo surfaces: CI workflows, test suites, code-quality paths, docs/examples, or whole-repo fallbacks.
3. Identify recurring work that might be automatable.
4. Propose labeled loop hypotheses from repo signals when a valuable loop might exist but has not been proven yet.
5. Rank options by leverage, gate strength, effort, and risk.
6. Route each option to the right path: plain scheduler, human-in-loop, L2 candidate, discovery required, or do not automate.
7. Stop before building or scheduling anything.

The product claim is:

> Find automation candidates, reject bad ones, and turn good ones into gated loop specs.

Not:

> Point it at a repo and it builds loops.

## CLI

```bash
super-looper repo audit --repo-path ../target-repo --out repo-audit
```

Artifacts:

- `repo-audit.json` - full machine-readable result.
- `gate-inventory.json` - discovered commands with source, category, strength, and safety notes.
- `repo-surfaces.json` - bounded surfaces that gates appear to exercise, such as a workflow, test suite, docs/examples surface, or lint/typecheck surface.
- `automation-candidates.json` - ranked candidate portfolio.
- `loop-hypotheses.json` - creative, explicitly unproven opportunities inferred from repo signals, with proposed verifiers and discovery questions.
- `ranked-backlog.md` - human-readable ranked backlog.
- `recommendations.md` - best next moves and guardrails.

## Interpretation Rules

- `confirmed_by_static_config` means a command was found in repository evidence. It does not mean the command has passed.
- `weak` gates, such as `compileall`, are canaries. They do not prove behavioral correctness.
- `plain_scheduler` means no agentic loop is needed; run the command on a timer and report.
- `human_in_loop` means an agent may draft work, but a human is still the gate.
- `l2_candidate` means there is enough static evidence to design a guarded loop candidate, not enough to schedule it unattended.
- `discovery_required` means the task might be valuable but lacks a trustworthy verifier.
- `do_not_automate` means the request is too broad, subjective, or unsafe as stated.
- `surface_id` on a candidate means the candidate is tied to a bounded repo surface. Prefer these over whole-repo candidates because they give clearer path fences and cleaner case studies.
- `hypothesis: true` means Super Looper is imagining a plausible loop from repo signals. It is useful for discovery, but it is not a confirmed automation candidate until the proposed verifier is built and run.
- Static repo audit never grants L3. L3 requires a proven manual pass, explicit unattended trigger, strong end-to-end tool gate, scope fence, budget cap, and reversible output.

## Good Follow-Ups

After audit, choose one candidate and create a case study:

1. Run the selected gates once on a clean checkout.
2. Measure runtime and flakiness.
3. Define exact `may_touch` and `must_not_touch` fences.
4. Produce a loop spec only if the gate can reject bad work objectively.
5. Keep broad requests like "make the repo better" rejected until rewritten as a specific recurring task.
