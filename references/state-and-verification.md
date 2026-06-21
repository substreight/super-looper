# State Architecture and Verification

The two design choices that most determine whether a loop converges cheaply and honestly. Read when choosing how state persists, or when designing a gate. The load-bearing empirical claims below (self-correction is unreliable, same-model judges self-prefer, context rot, verifiable rewards) are sourced in `evidence.md`.

## Part 1 — State architecture: fresh-restart vs compaction

A naive loop keeps everything in the conversation: each pass re-sends the goal, the work so far, and every prior tool result. This fails two ways at once — cost compounds (ten passes ≈ ten growing copies of context), and quality degrades because recall drops as context grows ("context rot," a measured effect of attention spreading thin over more tokens). Don't fix this by trimming. Keep durable state outside the model and give each unit of work a clean-ish context. Two patterns:

### Fresh-context restart
Each iteration is a new instance. It reads minimal state from disk (a plan file, `progress.txt`, the last failure), does one scoped item, writes state back, and exits. History lives in files and version control, not the context window.

- **Best when:** the task decomposes into independent items, each with a checkable result (tasks in a plan, files to migrate, tickets to process).
- **Watch for:** the brute-force version ("re-run the same prompt in a `while` loop until something passes," the bare "Ralph" technique) is token-hungry and ships broken work without a gate. Use the disciplined form: one item per pass, a real verifier, hard iteration/budget caps, and no-progress detection.

### Compaction
Keep one session, but when it nears the context limit, summarize and reinitialize with the summary plus the few most-relevant artifacts. Merge new facts into a *persisted, growing* summary rather than regenerating it from scratch each time — anchored/iterative summarization measurably preserves more than full reconstruction.

- **Best when:** the work is one continuous reasoning thread that doesn't cleanly split, and continuity of subtle context matters.
- **Watch for:** over-aggressive compaction silently drops a detail whose importance only appears later. Tune the summary prompt for recall first, then precision.

### Decision rule
Splits into independent, individually-checkable items → fresh-context restart. One continuous thread → compaction. In both, the plan and progress live in files, and the model's working context stays small.

## Part 2 — The verifier ladder

The gate is the loop's design. Rungs, highest trust first:

### Rung 1 — Tool / computational gate
Tests, build, type checker, linter, schema validation, a numeric threshold. Deterministic and unarguable. This is why code loops are the most reliable kind of loop, and why the frontier of model training itself leans on *verifiable* rewards. If you can manufacture a tool-based gate (even a cheap one — a schema, a smoke test), do it before reaching for a model judge.

The strongest form exercises the real system end-to-end instead of trusting a self-reported result: hit a live endpoint and assert on the response, drive the actual UI in a browser, run the build in a simulator. For loops running unattended, this end-to-end check is the load-bearing safeguard — auto-approved permissions, fan-out, and cloud execution are only safe because something independently confirms the real system still works. A loop that "passes" its own unit assertions but was never run against reality is the classic way confidently-wrong work ships overnight.

### Rung 2 — Independent model critique
A *different* model, at least as capable as the maker, evaluating against an explicit rubric. Two design rules that most setups miss:

- **Withhold the maker's justification.** Give the checker the artifact and the criteria, not the maker's argument for why it's done. A confident, well-argued-but-wrong rationale can persuade a judge into approving bad work, and capability raises persuasiveness faster than it raises error-detectability. Anchoring the checker on the maker's reasoning defeats the point of an independent gate.
- **Account for self-preference.** Models recognize and favor their own generations, so a same-model checker is the weakest form of this rung. Prefer a different model/family.

For borderline outputs, use confidence-tiered routing instead of binary pass/fail: clear pass → accept; uncertain → log and flag for human; fail → block and report.

### Rung 3 — Human gate
For irreducibly subjective "done." Legitimate, but it makes the loop human-in-the-loop, not autonomous. Say so; don't dress a human-gated workflow up as an autonomous loop.

### Off the ladder — the maker grading itself
Self-checking as the *sole* gate is not a weak gate, it's frequently a negative one. The assumption that verification is easier than generation does not reliably hold for LLMs: without external feedback, self-correction often leaves reasoning unchanged or *worse*, and seeing its own proposed solution can make a model *less* calibrated about whether it's right. Use self-scoring only as a refinement aid (the portable Template 2 loop), never as the gate for anything the model can be confidently wrong about. If no rung-1 or rung-2 gate is available and the task can't tolerate a human gate, the honest conclusion is that the task is not yet a loop.
