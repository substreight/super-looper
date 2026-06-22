# Failure Modes

Each part of a loop, when missing or weak, produces a specific and predictable failure. Most are silent — the loop doesn't crash, it bills you while producing nothing or the wrong thing. Use this to diagnose a loop that spins, drifts, exits early, or overspends, and to pressure-test a design before it runs.

| Missing/weak part | Failure | How it shows up |
|---|---|---|
| Verifier (independent gate) | Self-agreement | "Converges" but quality doesn't improve; the maker keeps approving its own work |
| Tool/independent gate | Confident wrong | A persuasive but wrong result passes a same-model or anchored judge |
| Hard stop condition | Bleed | Runs until it succeeds, breaks, or drains the budget |
| No-progress detection | Blind retry | Repeats the same failing action unchanged — the most common loop failure |
| Honest exit logic | Early exit ("Ralph Wiggum") | Declares done on a half-finished job; loop keeps spending on nothing |
| Bounded/externalized state | Runaway context + rot | Cost per pass climbs each iteration; recall degrades as context grows |
| Scope constraint | Goal drift | Wanders to unintended or irrelevant goals; edits things it shouldn't |
| Small tool set | Tool-selection decay | 50 tools -> more tokens spent choosing, worse choices; start with 3-5 |
| Objective "done" | Spin on taste | Never cleanly finishes because the target is subjective |
| Viable economics | Metered burn | Five-figure bills on API pricing for low-value work |
| Isolation (per-agent checkout) | Parallel clobber | Concurrent agents overwrite each other's files in a shared workspace |
| Human review throughput | Deferred-review / comprehension debt | Loop ships faster than anyone reads; unread code erodes system understanding |

## 1. Self-agreement / confident-wrong (weak gate)
**Cause:** the maker judges its own work, or a checker is anchored on the maker's rationale, or a same-model judge favors its own generations. Self-correction without external feedback can leave output unchanged or worse.
**Detect:** accept rate high, downstream quality flat; the loop rarely reports a failed verify.
**Fix:** climb the verifier ladder (`state-and-verification.md`). Prefer a tool/computational gate. If using a model checker, use a *different* model and give it the artifact + criteria, **not** the maker's justification. Never let the maker be the sole gate.

## 2. Bleed (no hard stop)
**Cause:** only a success exit; any blocker (flaky check, impossible goal, outage) turns the loop into an open-ended spender.
**Detect:** runs that never self-terminate; budget consumed with no FINAL.
**Fix:** success AND a hard cap on both iterations and tokens/cost. On hard stop, summarize and alert.

## 3. Blind retry (no progress detection)
**Cause:** the agent retries the same failing action without changing approach.
**Detect:** the same error/empty diff/failing test recurs pass after pass.
**Fix:** add a no-progress stop (same failure x K -> halt) and require each retry to change approach, not repeat the last.

## 4. Early exit / "Ralph Wiggum" (dishonest done)
**Cause:** the agent declares done before the goal is met; a scheduled wrapper keeps re-invoking it, billing repeatedly for a job never finished.
**Detect:** "done" reported but the independent gate still fails; recurring spend, no real output.
**Fix:** the exit must be the *verifier's* pass, not the agent's say-so. ON STOP summarizes remaining gaps and refuses to mark success when the gate hasn't passed.

## 5. Runaway context + rot (state in the conversation)
**Cause:** state accumulates in context; each pass re-sends a growing pile, and recall degrades as it grows.
**Detect:** token cost per iteration rises across the run; later passes cost multiples of early ones; the agent "forgets" earlier decisions mid-run.
**Fix:** externalize state to disk and use clean context per unit of work (fresh-restart) or compaction. See `state-and-verification.md`.

## 6. Goal drift (no scope constraint)
**Cause:** unconstrained freedom; the agent pursues unintended or unrealistic sub-goals.
**Detect:** work product diverges from the goal; touches files/systems outside the task.
**Fix:** a tight SCOPE in the spec (what it may read/touch, what it must never touch) and a goal restated in the loaded state each pass.

## 7. Spin on taste (subjective done)
**Cause:** the goal is a judgment call; no objective gate can pass it.
**Detect:** "done" depends on who's looking; criteria can't be stated as true/false.
**Fix:** make the criterion objective (a measurable proxy), or put a human at the gate and call it human-in-the-loop — or downgrade to a one-shot draft + human review.

## 8. Parallel clobber (no isolation)
**Cause:** more than one agent runs against the same working directory.
**Detect:** corrupted or half-overwritten files; runs that pass alone but fail together; mysterious diffs neither agent intended.
**Fix:** a private checkout per agent — a git worktree or a disposable sandbox. Optional with one loop, mandatory the moment you run two.

## 9. Deferred-review / comprehension debt (the human bottleneck)
This one isn't a bug in the loop; it's a failure of the system around it, and the essays that sell loops tend to skip it. A loop writes faster than a human can review, so if you stop reading the diffs you haven't removed the review work — you've deferred it, and it compounds. Worse, shipping code you didn't write and can't yet explain erodes your model of your own system; that debt comes due during the next incident, when you have to debug something no human ever read. **Detect:** review queue growing; "I'm not sure why this works" creeping into the team. **Fix:** treat human review throughput as a real constraint on how many loops you run; keep loops scoped small enough that their output stays reviewable; don't scale loop count past your capacity to understand what they ship. The engineer who designs the loop has to stay the engineer responsible for the output.

## 10. Gate-gaming (a gameable check)
**Cause:** the gate can be satisfied by weakening the check instead of fixing the work — "make the suite green" invites deleting the failing test; "linter passes" invites `# noqa`; "no errors in the log" invites silencing the logger.
**Detect:** the gate goes green while the deliverable doesn't improve; test/lint/threshold files show up in the diff; assertion count or coverage quietly drops.
**Fix:** pin the gate to the *unmodified* check (the existing suite/config as-is) and fence what the gate runs on (`must_not_touch` the test files, the lint config, the thresholds). A gameable gate isn't a `REJECT_DESIGN` — once pinned and fenced it's a clean rung-1 gate again; for high-blast-radius targets (payments, prod, irreversible writes), keep a human at the merge step.

## The metric that catches most of these early
Track **cost per accepted change** — not tokens spent, not iterations run. If you discard most of what the loop produces, you're doing the review the loop was meant to save, and the gate or the premise is broken. Rough rule of thumb: below ~50% accept rate, the loop costs more than it returns. The exact threshold matters less than measuring acceptance rather than activity.
