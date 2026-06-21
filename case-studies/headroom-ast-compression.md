# Headroom AST Compression Case Study

Run date: 2026-06-21

Target repo: https://github.com/chopratejas/headroom

Target issue: https://github.com/chopratejas/headroom/issues/1233

## Why This Target

Headroom is a useful public stress test for Super Looper because it is a real, active codebase with mixed Python/Rust packaging, CI, transform logic, tests, and open issues that are concrete enough to gate.

The selected issue is especially useful because it has an objective failure shape: AST code compression can emit invalid Python syntax, and the loop can be judged by a corpus test plus a numeric rejection threshold. That makes it much better than a vague "improve quality" task.

## Generated Loop

Source interview answers:

```text
examples/headroom-ast-compression.answers.json
```

Case-study manifest:

```text
case-studies/headroom-ast-compression/case-study.json
```

Compiled loop spec:

```text
examples/headroom-ast-compression.loop.json
```

Reproduce:

```bash
super-looper interview --answers examples/headroom-ast-compression.answers.json --out examples/headroom-ast-compression.loop.json
super-looper validate examples/headroom-ast-compression.loop.json --strict
super-looper render examples/headroom-ast-compression.loop.json --strict
super-looper max-autonomy examples/headroom-ast-compression.loop.json --json
```

Run the local case-study harness against an already-cloned Headroom checkout:

```bash
super-looper case-study design case-studies/headroom-ast-compression
super-looper case-study resolve-verifier case-studies/headroom-ast-compression --repo-path ../headroom-loop-case
super-looper case-study resolve-verifier case-studies/headroom-ast-compression --repo-path ../headroom-loop-case --no-shadow
super-looper case-study run case-studies/headroom-ast-compression --repo-path ../headroom-loop-case
super-looper case-study simulate-verifier case-studies/headroom-ast-compression --repo-path ../headroom-loop-case --template python-ast-corpus
super-looper case-study verify case-studies/headroom-ast-compression/runs/<run-id>
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for maintainer
super-looper case-study report case-studies/headroom-ast-compression/runs/<run-id> --for pr
```

`simulate-verifier` writes proposed verifier code under the run artifact directory and executes it from there, leaving the target checkout untouched. Treat a pass as shadow evidence only: useful for a maintainer report or proposed test patch, not as upstream CI proof.

Expected result:

```text
OK: valid loop spec (0 warning(s))
max_autonomy: L2
```

## Verdict

This is a valid guarded loop design, not a scheduler job and not a rejected design.

It earns L2 because it has:

- a concrete objective gate: corpus compression check exits 0 and invalid syntax rejection rate is at or below 10%
- a scoped work area: compression transform, transform tests, fixtures, and progress state
- explicit must-not-touch boundaries
- machine budget cap
- reversible output
- end-to-end tool verification

It does not earn L3 yet because it lacks:

- a proven manual pass on the target repo
- an explicit unattended trigger

That is the right answer. A high-attention public repo should not be used to demonstrate "autonomy" by skipping empirical proof. The first public proof point should be a clean L2 design and a manual run that records exactly what passed.

## What This Proves

The interview compiler can take a real open-source issue and produce a machine-valid loop spec without asking the human for perfect answers or hallucinating missing guarantees.

The autonomy dial is doing real work here. It does not flatten "good idea" into "run it unattended." It says:

```text
run this with guardrails first; earn unattended later
```

## Next Upgrade

The next public-facing upgrade would be a runnable case-study harness that:

1. clones the target repo into a temporary worktree
2. records repo metadata and selected issue context
3. compiles the loop spec from an answers fixture
4. runs the declared verifier if the target repo dependencies are available
5. writes a compact result artifact under `case-studies/results/`

That would move Super Looper from "design compiler" toward "loop design benchmark," while still keeping execution gated and explicit.
