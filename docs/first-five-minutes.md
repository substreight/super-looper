# First five minutes with Super Looper

Most proposed agentic loops should not run. Super Looper's first job is to say
**no** unless the task has a real gate, bounded scope, state outside the context
window, and hard stop conditions.

The golden path is:

```bash
super-looper decide --answers answers.json
super-looper check loop.json
super-looper run loop.json --propose "<model command>" --verify "<gate command>"
```

## 1. Start with `decide`

Use `decide` when you have a task idea and need to know whether it is a loop at
all.

```bash
super-looper questions
super-looper decide --answers examples/unknown-gate.answers.json
```

Read the verdict:

- `DISCOVERY_REQUIRED`: do not build the loop yet; gather the named evidence.
- `HUMAN_IN_LOOP`: useful as a draft/propose workflow, not autonomous.
- `USE_SCHEDULER`: a fixed script/cron/CI job is better than an agent.
- `REJECT_DESIGN`: the design violates a hard rule, usually self-grading.
- `AUTONOMOUS_LOOP`: a spec can be generated and checked.

`decide --json` keeps the machine-readable shape for scripts.

## 2. Check the spec in one card

```bash
super-looper check examples/nightly-export.loop.json
```

`check` tells you:

- whether the spec validates,
- what the loop will do in plain English,
- the requested autonomy,
- the maximum safe autonomy it actually earned,
- what is missing before it can earn more.

If `requested` is higher than `max safe`, fix the spec or dial autonomy down.

## 3. Run only after the gate is real

```bash
super-looper run loop.json --propose "..." --verify "..."
```

The runtime owns only the deterministic skeleton: iteration cap, budget cap,
state checkpointing, keep/revert, and no-progress stop. Your environment owns
the model command, verifier command, credentials, and sandbox.

## 4. Use `lab` for discovery, not core UX

Repo audit, case studies, and remote-runner planning are lab tools:

```bash
super-looper lab repo audit --repo-path . --verify-gates
```

`--verify-gates` runs discovered verifier commands and records whether each gate
passed, failed, timed out, or was skipped. Candidates that rely on failed or
unverified gates are downgraded; a static-looking gate is not treated as proof.

## 5. Sanity-check the install

```bash
super-looper doctor
```

`doctor` is offline. It reports the installed version, validator mode, example
spec status, and whether any perimeter modules loaded in the process.

