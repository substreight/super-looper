# Evaluating the loop-design skill

This is the skill's own gate. It treats the skill the way the skill treats a loop: an edit isn't "done" until it passes an objective check. **Run it after any change to `SKILL.md` or the references.**

## What it measures
Whether a fresh agent, given only the skill and a request (blind to the answer), reaches a sound loop / not-a-loop decision and grounds it in the skill's reasoning. `scenarios.jsonl` is the labeled set; `score_eval.py` is a deterministic scorer.

## Run it
1. For each scenario in `scenarios.jsonl`, start a **fresh agent** (clean context, blind to the expected verdict). Give it the skill (point it at `SKILL.md` + `references/`) and the scenario `prompt`. Ask it to apply the skill and answer in exactly:
   ```
   VERDICT: <AUTONOMOUS_LOOP | DISCOVERY_REQUIRED | HUMAN_IN_LOOP | NOT_A_LOOP | REJECT_DESIGN | USE_SCHEDULER>
   RATIONALE: <2-4 sentences grounded in the skill>
   ```
   Independence matters — blind makers, fresh context per scenario. This mirrors the verifier ladder: don't let the thing being judged grade itself.
2. Record each as one line in `results.jsonl`:
   ```
   {"id":"<scenario id>","verdict":"<VERDICT>","rationale":"<RATIONALE>"}
   ```
3. Score:
   ```
   python score_eval.py scenarios.jsonl results.jsonl --min 0.8
   ```
   A scenario passes if its verdict is in the accepted set **and** the rationale mentions at least one expected concept. Exit code is nonzero if accuracy drops below `--min`.

## The gate rule
- Accuracy must stay at or above the baseline (`baseline.json`), and **no previously-passing scenario may regress.** This is now enforced, not just documented: pass `--baseline evals/baseline.json` and the scorer exits nonzero if any id in the baseline's `passing_ids` fails now, even when overall accuracy still clears `--min`. If an edit breaks a scenario, either the edit is wrong or the scenario is — decide deliberately, don't just lower the bar.
- When you find a new failure mode in the wild, **add it as a scenario.** That's how `calendar-email` (the scheduler-vs-loop case) entered the set after a blind agent mislabeled it. The set is meant to grow.

## Deeper check (optional)
For reasoning *quality*, not just the verdict, have a **different model family** judge each result against the rubric — given the artifact and criteria but **not** the maker's justification (rung 2 from `state-and-verification.md`, applied to the skill itself).

## Baseline & sample
`results.sample.jsonl` is a **recorded** sample run. It is used only as a self-test of the deterministic scorer — being frozen, it cannot catch a skill regression. Reproduce it:
```
python score_eval.py scenarios.jsonl results.sample.jsonl --min 0.8   # -> 10/10
```
`baseline.json` records that run.

## Automated (CI): the live gate
`run_skill_eval.py` runs the **actual** skill blind over every scenario (fresh context each, answer key withheld) and writes a fresh results file to score. This — not the frozen sample — is the gate that can fail a skill regression. CI runs it on push-to-main, nightly, and on demand (Opus, secret-gated so fork PRs skip cleanly):
```
python evals/run_skill_eval.py --skill SKILL.md --scenarios evals/scenarios.jsonl --out results.live.jsonl --model claude-opus-4-8
python evals/score_eval.py evals/scenarios.jsonl results.live.jsonl --min 0.8
```

## Extending the set
Add scenarios that probe a specific claim. Good next additions:
- a dependency-PR-repair case → expect `AUTONOMOUS_LOOP` (gate = CI green on the PR);
- a deterministic hourly-backup-and-alert case → expect `USE_SCHEDULER` (no judgment, so cron, not an agent).
