# Evidence

The skill argues from a small set of findings rather than from hype. None of this is settled industry practice — the vocabulary is barely a year old — but the load-bearing claims below are grounded in real work you can check. Verify a source before leaning on it; don't take the skill's word for it.

## Why self-checking is off the verifier ladder
**Huang, J. et al. (2024). "Large Language Models Cannot Self-Correct Reasoning Yet." ICLR 2024.** — [arXiv:2310.01798](https://arxiv.org/abs/2310.01798)
Without external feedback, intrinsic self-correction on reasoning tasks leaves answers unchanged or makes them worse. → The maker grading its own work isn't a weak gate, it's often a *negative* one (`state-and-verification.md`, "off the ladder"; `SKILL.md`, the verifier ladder).

## Why a same-model checker is the weakest rung 2
**Panickssery, A. et al. (2024). "LLM Evaluators Recognize and Favor Their Own Generations."** — [arXiv:2404.13076](https://arxiv.org/abs/2404.13076)
Models recognize their own outputs and, as evaluators, rate them higher than equal-quality work from others; self-recognition strength correlates with self-preference. → Prefer a *different* model/family for the gate, and withhold the maker's justification (`state-and-verification.md`, rung 2).

## Why state lives on disk, not in the context ("context rot")
**Liu, N. F. et al. (2024). "Lost in the Middle: How Language Models Use Long Contexts." TACL 12:157–173.** — [arXiv:2307.03172](https://arxiv.org/abs/2307.03172)
Performance is highest when relevant information sits at the start or end of the context and degrades when it's in the middle — even for long-context models.
**Hong, K., Troynikov, A., Huber, J. (2025). "Context Rot: How Increasing Input Tokens Impacts LLM Performance." Chroma technical report.** — [trychroma.com/research/context-rot](https://www.trychroma.com/research/context-rot) · **Modarressi, A. et al. (2025). "NoLiMa: Long-Context Evaluation Beyond Literal Matching." ICML 2025.** — [arXiv:2502.05167](https://arxiv.org/abs/2502.05167)
Accuracy degrades measurably as input grows, across frontier models, even on simple retrieval. → Keep durable state outside the model and give each unit of work a clean-ish context (`state-and-verification.md`, Part 1; `failure-modes.md`, "runaway context + rot").

## Why a tool/computational gate is the strongest rung
**Lambert, N. et al. (2024). "Tulu 3: Pushing Frontiers in Open Language Model Post-Training."** — [arXiv:2411.15124](https://arxiv.org/abs/2411.15124) · **DeepSeek-AI (2025). "DeepSeek-R1." Nature 645:633–638.** — [arXiv:2501.12948](https://arxiv.org/abs/2501.12948)
Reinforcement learning from *verifiable* rewards (RLVR) — correctness signals from deterministic verifiers rather than preference labels — is load-bearing at the training frontier. → The same logic the frontier leans on is why code loops with a real tool gate are the most reliable kind (`state-and-verification.md`, rung 1).

## Honest caveat
These support the *principles*; they don't validate any specific loop you build. The named loop techniques ("Ralph," evaluator-optimizer, harnesses) are mostly evidenced by blog posts, not controlled evaluation. Design from the principles; treat the techniques as options with tradeoffs.
