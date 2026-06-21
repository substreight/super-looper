# Loop Spec Templates

Filled templates at increasing weight. Pick the lightest one that meets the need — the portable template (2) covers most everyday tasks with zero infrastructure. Adapt the bracketed parts; keep the structure. All assume the design choices in `state-and-verification.md` (clean context per unit of work, gate by ladder rung). Templates 4–5 are proven instances pulled from real use — adapt them to a new invariant or a weak gate.

## Contents
- Template 1 — Rigorous code / CI loop (hard gate, real tooling)
- Template 2 — Portable self-checking loop (paste into any chat model, no tooling)
- Template 3 — Lightweight scheduled / event automation
- Template 4 — Invariant → self-verifying regression-test backfill
- Template 5 — Gate-coverage strengthener
- Worked example — taking a vague ask through the design workflow

---

## Template 1 — Rigorous code / CI loop

Use when a rung-1 gate exists (tests, build, types, lint). The strongest kind of loop because the gate can't be argued with. Runs fresh-context restart: one item per pass, state on disk.

```
GOAL:        every test in /tests/<area> passes, lint clean, zero type errors.
SCOPE:       may edit <allowed paths>; never touch <protected paths> or delete tests.
EACH ITERATION (clean context):
  1. read IMPLEMENTATION_PLAN.md + progress.txt + last failure
  2. run tests, lint, type checker; pick the single highest-impact failure
  3. write the smallest change that fixes it; if retrying, change approach
  4. re-run the verifier; append outcome to progress.txt; commit; exit
VERIFY:      green tests AND zero lint warnings AND zero type errors (rung 1)
STATE:       on disk — plan file, progress.txt, git history
STOP WHEN:   verify passes  OR  8 iterations  OR  <token budget>  OR  same failing
             test 3x in a row
ON STOP:     summarize each change made and every failure still open
REPORT:      post summary + diff to <channel/PR>
MAKER:       fast/cheap model
CHECKER:     the test suite itself (rung 1); optional different-model review of the
             diff for scope creep, given the diff but NOT the maker's rationale
```

Note: the test suite *is* an independent checker, which is why code loops are easy to get right. Add a model-checker only for things tests miss (scope creep, deleted/weakened tests, hardcoded passes).

---

## Template 2 — Portable self-checking loop

Use when there's no tooling — just a chat model. Gives the model a goal, strict criteria, and a self-check protocol in one message.

**Honest limit:** here the gate is the model judging itself (off the verifier ladder). Self-correction without external feedback often doesn't improve the work and can degrade it, and the model is a poor judge of its own correctness. So this is a *drafting and refinement aid*, not a gate — good for prose, structure, and surfacing weak spots; unsafe as the sole check for anything the model can be confidently wrong about (facts, code correctness, calculations). Strengthen it by running the VERIFY step in a fresh chat or a different model than produced the work.

```
You will work in a loop until the task meets the bar.

TASK:
[describe exactly what you want produced]

SUCCESS CRITERIA (strict, no soft passes):
- [criterion 1]
- [criterion 2]
- [criterion 3]

LOOP PROTOCOL, every turn:
1. PLAN   — state the single next step.
2. DO     — produce or improve the work.
3. VERIFY — score the result 1-10 on each criterion. Be brutally honest;
            list exactly what is still weak.
4. DECIDE — if every criterion is 8+, print "FINAL" and stop.
            Otherwise print "ITERATING" and go again, fixing the weakest
            point first (a different fix than last turn).

RULES:
- Never call it done until every criterion is 8+.
- Each pass must fix the weakest score from the last VERIFY.
- Don't ask me questions; make a sensible assumption, note it, continue.

Begin. Run the loop until FINAL.
```

When to upgrade: only once you've felt this isn't enough — you need it unattended, scheduled, or event-triggered, *or* you need a gate the model can't fool itself on. That's the jump to a real tool-based gate (Template 1) or hosted machinery. Don't make the jump pre-emptively.

---

## Template 3 — Lightweight scheduled / event automation

For recurring life/ops jobs where the gate is a simple rule and the value is that it runs unattended.

```
TRIGGER:     [time, e.g. weekdays 7:00am]  OR  [event, e.g. inbound email matches X]
SCOPE:       [which accounts/sources; read-only vs allowed to act]
ACTION:      1. [read source(s) — calendar, inbox, sheet, API]
             2. [transform — summarize / extract / file / decide]
             3. [act or deliver — send / post / create ticket / notify me]
VERIFY:      [the simple rule that means it did the job, e.g. "brief <=120 words,
             names 3 items"]  — or human glance if truly subjective
STATE:       [on disk: last-seen marker, what was already actioned, streak]
STOP/GUARD:  [skip if nothing to report; cap actions per run; rate limit; budget]
REPORT:      [where the output lands]
```

Reality check before recommending this: it still needs Step 0 qualification. If "done" is subjective ("write a *good* post"), it isn't an autonomous loop — it's a draft generator with you as the gate. That's fine; name it honestly.

---

## Template 4 — Invariant → self-verifying regression-test backfill

Use when an audit or incident found a property that should always hold (an authorization boundary, an input-validation rule, an invariant) and you want it enforced permanently so it can't silently regress as new code is added. The loop's output is durable rung-1 tests; its gate is self-checking.

```
GOAL:        every <site> (e.g. mutation route) that should enforce <invariant> has a
             test proving a violation is rejected.
  evidence:  the suite is green AND each new test FAILS when the guard is removed
  constraints: only ADD tests; never edit the code under test; never weaken existing tests
  budget:    <N sites/run>, <K iters/site>, token cap
SCOPE:       may touch test files + test helpers; never the implementation or config
EACH ITERATION (clean context, one site per pass):
  1. read progress + the target site + a sibling site that already enforces the
     invariant (the oracle)
  2. write a test asserting a violation is rejected (and that no forbidden state changed)
  3. STAGE A — run the suite; the test must pass on current code
  4. STAGE B (test-the-test) — stub out the site's guard, re-run the one test, confirm
     it now FAILS, then restore the guard
  5. if it can't be made to fail in Stage B, the site may be UNGUARDED -> flag it
VERIFY:      suite green (rung 1) AND stub-the-guard makes the new test fail (rung 1 on
             the gate itself)
STATE:       on disk -- sites covered / failed; the invariant as durable context
STOP:        all sites covered  OR  N iters  OR  budget  OR  a site yields no
             discriminating test xK
ON STOP:     open a PR with the tests + a list of sites with no working guard (candidate
             bugs); never claim done if the suite is red
MAKER:       cheap model/site   CHECKER: the suite + the stub-the-guard step
ISOLATION:   worktree
```

**Why the test-the-test is load-bearing:** the classic failure of "agent writes tests" loops is tests that pass while asserting nothing. Requiring each test to *fail* when its guard is removed converts a prose claim ("this is covered") into a proven, discriminating rung-1 gate. **The "could not make it fail" set is the prize** — those sites lack the guard, i.e. live findings. **Needs an oracle:** it works because a sibling site shows what the invariant should be; a site with no guarded sibling has nothing to learn from — list those for a human to specify.

---

## Template 5 — Gate-coverage strengthener

Use when a gate already exists but checks the *plumbing*, not the *deliverable* — it confirms an action happened (HTTP 200, "the names match") while the thing you actually care about (the payload, the field values, the content) goes unchecked. This is the most common way a loop "passes" while shipping wrong work (see `failure-modes.md`: confident-wrong). Strengthening the gate is often higher-leverage than any new loop.

```
GOAL:        the gate rejects a bad version of <the deliverable>, not just a missing <action>.
  evidence:  the strengthened check FAILS on a seeded defect in the deliverable, PASSES
             when correct
  constraints: extend the existing gate; don't weaken its current checks
  budget:    small -- usually one focused change
SCOPE:       the gate/check itself + whatever it must parse; not the system under test
STEPS (usually one pass, not an iterating loop):
  1. name what the gate checks vs what the deliverable actually requires (the coverage gap)
  2. extend the check to cover the deliverable (compare the fields/content, not the envelope)
  3. run it against current state -- latent drift it now catches is a real finding; report it
  4. TEST-THE-TEST: seed a defect in the deliverable -> the gate must fail naming it; restore
  5. wire the strengthened gate into CI so it actually runs
VERIFY:      strengthened check fails on a seeded defect AND passes on the corrected state
ON STOP:     report any latent defects the stronger gate surfaced; commit the gate + CI wiring
```

**This is often NOT an LLM loop.** If the stronger check is deterministic (codegen, a parser, a diff), build the *script*, not an agent. The LLM earns a place only where the mapping needs judgment. **The diagnostic question (Step 0):** does the gate reject a bad version of the thing you actually want, or merely confirm the action happened? If the latter, strengthen it before trusting any loop that depends on it.

---

## Worked example — vague ask -> clean spec

**User asks:** "Set up an agent that keeps improving our onboarding email until it's good."

**Qualify:** Recurs? No — one-time asset. Objective "done"? No — "good" is taste. Two boxes fail → **recommend against a loop.** Use one strong drafting prompt, or Template 2 with the user as the real gate. Say so directly rather than building a loop that spins on a subjective target.

**User reframes:** "Run our nightly data export and don't let it silently produce a malformed file."

**Qualify:** Recurs nightly. Auto-rejectable (schema validation, rung 1). End-to-end. Objective done (valid schema + row count > 0). Economics fine (cheap, scheduled). All pass.

**Spec:**
```
GOAL:        nightly export validates against schema AND row_count > 0
SCOPE:       read export pipeline + write the output file only
TRIGGER:     daily 02:00
EACH ITERATION (max 3 on failure, clean context):
  1. run export
  2. validate file against schema; check row count
  3. if invalid, read the validation error, retry with the documented fix
     (different fix than last attempt)
VERIFY:      schema valid AND row_count > 0 (rung 1)
STATE:       last successful run timestamp; this-run attempt log
STOP WHEN:   verify passes  OR  3 attempts  OR  same validation error 2x
ON STOP:     if still failing, alert with the exact validation error — do NOT
             mark the run successful
REPORT:      success -> log; failure -> page on-call with the error
```
The gate (schema + row count) was designed first; the loop body exists only to satisfy it.
