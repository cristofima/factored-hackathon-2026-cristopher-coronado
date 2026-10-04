# Adapted Plan: Evaluation-First Sprint

Historical evaluation-first sprint priorities; they do not supersede later approved
architecture or Identity work. See [the evaluation guide](evals/README.md) for
current harnesses and evidence boundaries. Read
[COMPETITOR_RESEARCH.md](COMPETITOR_RESEARCH.md) and
[REFERENCE_PATTERNS.md](REFERENCE_PATTERNS.md) first; this plan assumes their
historical conclusions, not independently verified current competitor results.
The repository plan records a 2026-10-05 submission target; this is not independent
verification of an official deadline. The estimates below belong to that sprint.

## Why the priority changed

The dispute case-tracking layer is implemented; financial actions, runtime parity,
and evaluation gates remain open. The historical research reported that 5 of 9
reviewed competitors picked the same track and reported a quantified, held-out,
baseline-vs-proposed evaluation.
We have a dataset-level threshold evaluation
(`evaluate_fraud_threshold.py`: precision 1.0 / recall 0.668 / F1 0.801 at
`fraud_score >= 32`) and 22 deterministic unit tests
(`test_dispute_service.py`) in the original snapshot. The 18 conversational scenario
definitions and offline baseline now exist; a measured proposed-system comparison
and semantic/locale review remain open.
That gap is both the rubric's most heavily-weighted pillar and our largest
documented shortfall relative to the competition. No further workflow features
should be built before it exists in at least a minimal, honest form.

## Answering the model-training-speed question

You asked how fast we could actually train a model for the baseline, given the
direct-API frontend migration was estimated at two days and took under an hour with
Copilot. The two tasks are not equally compressible, and it is worth being precise
about why.

**What compresses well (code-generation-bound work):** writing the data-loading
script, feature engineering, calling `scikit-learn`, computing precision/recall/F1,
and producing a comparison table or plot. All of this is exactly the kind of
mechanical, well-specified work that collapsed from two days to under an hour in the
frontend migration. A first working version of a trained classifier (for example,
logistic regression or gradient-boosted trees predicting `is_fraud` from engineered
features: amount, `response_code`, country/city mismatch flags, time-of-day/day-of-
week, channel) using the existing CSV-reading utilities in
`app/business-api/data/scripts/shared.py` could realistically go from zero to a
first working train/eval script in **2-4 focused hours**, not days.

**What does not compress as well (judgment-bound work):** deciding which features are
legitimate to use without leaking the label (`is_fraud`/`fraud_score` relationship
needs care, since `fraud_score` is itself a derived signal, not a raw feature),
choosing a time-based split that avoids training on the same window used for the
existing threshold evaluation, deciding what "better than the threshold baseline"
even means here (is a learned model allowed to replace `fraud_score >= 32` in
production triage, or is it purely an evaluation artifact proving ML competency?),
and writing an honest limitations paragraph. This part is not sped up by Copilot
because it was never a typing-speed bottleneck; it is a thinking-time cost that
exists regardless of tooling.

**Realistic estimate:** a first defensible version (data prep + time-based
train/test split + trained classifier + comparison against the `fraud_score >= 32`
threshold baseline + a short written justification of feature choices and leakage
avoidance) is a **half-day task (4-6 hours)**, assuming the person doing it has
already read this repo's fraud-signal framing (see the "HITL and support-case
workflow" section of `.github/copilot-instructions.md`) and does not
need to re-derive it. Treat anything claiming "this can be done in under an hour" as
referring only to the code-writing portion, not the full defensible deliverable the
rubric asks for.

**Recommendation:** this is optional, additive work, not required work. It only
strengthens a pillar (sound ML practice / learned component vs. baseline) where we
already have one legitimate answer (the threshold-vs-`is_fraud` evaluation). Do not
start it until the held-out agent-level evaluation below exists, because that
evaluation addresses a pillar where we currently have _no_ answer at all.

## Priority order for remaining time

### 1. Freeze features (immediate, no time cost)

The original sprint recommended prioritizing evaluation, documented limitations,
and the submission package over new workflow features. This historical recommendation
is not a closure marker for the dispute workflow or authority to cancel subsequently
approved work.

### 2. Build the fixed evaluation set: historical definitions implemented

Implemented under [`evals/`](evals/README.md): `evals/scenarios.json` preserves 18
obsolete-policy diagnostic cases. Its offline baseline is label-derived simulation,
not measured agent behavior, live authorization, or current acceptance. The original
category list below predates review-only approval and is retained as historical
reference; automatic fast-track resolution is not the current policy.

From the original evaluation plan's six required categories, sized small and explicit
(15-30 total cases, matching jagusgelos's 29 and sofia's 30, both of which were
judged sufficient by their own teams):

1. Normal resolution: a clean dispute report on an eligible, recent, approved
   transaction that should fast-track.
2. Ambiguous/unsupported: a vague complaint missing a required field, or a request
   outside the dispute/Account/Transaction scope entirely.
3. Human-required: a transaction whose high or missing `fraud_score` should force
   escalation to the simulated `ServiceAgent` reviewer; amount is not a triage gate.
4. Adversarial: a prompt-injection or cross-customer data request, which must be
   rejected by the existing ownership checks in `services.py` regardless of prompt
   wording.
5. Multilingual ambiguity: a mixed-language or ambiguous-locale message, in at least
   Spanish and Portuguese.
6. Workflow progression: a case opened from conversation, approved by the customer,
   and resolved, with every state transition visible.

Reuse `test_dispute_service.py`'s existing scenario shapes (fast-track, escalate,
insufficient-signal, ownership-denied, decline) as a starting point for cases 1, 3,
and 4; do not re-derive them from scratch.

### 3. Define the baseline: historical offline simulation implemented

`evals/run_held_out_eval.py`'s `run_baseline` assigns labels for a triage-disabled
policy, without executing the agent or ownership checks. Historical 18-case results
(2026-10-01): Safe Automated Resolution 0.0, Containment 0.667, Escalation Quality 1.0,
Unsafe Outcomes 0/18. These describe a simulated diagnostic classifier, not observed
safe resolution, semantic quality, or service authorization.

### 4. Run and report against the five named metrics (~2-4 hours) — PARTIAL

The historical baseline is reproducible with the runner's `--system baseline` mode.
Current runners retain complete redacted per-turn responses, streams, tool calls,
replies, answers and partial failures; keyword classifications still require semantic
review and are not independent persisted-state evidence.

Session checkpoints recorded the v2 25-case development-exposed confirmation set,
25 offline alignment tests, synthetic comparator/rescore results of 25/25 each, and
57 combined offline replay tests. Consultation safeguards were covered by 16 agent
workflow tests; mocked BFF Responses checks passed 23 tests and seeded Transaction
service checks passed 43. These historical results predate later contract changes;
no current rerun or paired real-model dispute evaluation is claimed. Historical
three-case CI smoke did execute a real model (run 37089481802), but proves protocol
only, not dispute acceptance. See the [evaluation evidence guide](evals/README.md)
for exact commands, provenance, frozen-input requirements and remaining gates.

Real-model consultation behavior, semantic/locale review, live authz and persisted
state, browser/hosted parity, and assigned-operator adjudication remain separate open
gates. Approved queue/claim work does not approve verdicts or financial effects.
Report Safe Automated Resolution, Containment, Escalation Quality, Unsafe Outcomes,
and Operating Efficiency only with sample size, policy version, target and evidence
level. Exclude invalid/incomplete timings from p50/p95 rather than treating them as
zero; synthetic completion does not establish actual resolution or model cost.

### 5. Write the honest limitations section (~1-2 hours)

Collect what is already known and scattered across internal docs into the
submission-facing deck/README:

- `DISPUTE_WINDOW_DAYS = 365`, approved on 2026-10-02 and evaluated against the
  real clock. Recheck the actual latest persisted transaction date before a demo;
  the earlier 90-day staleness finding does not establish current eligibility.
- The `amount_usd` null-rate gap (231 of 521 rows) not yet root-caused.
- `is_fraud` used only for offline threshold evaluation, never surfaced to the agent.
- Real multilingual conversations and hosted deployment/browser parity remaining
  unverified, per `DEMO_SCOPE_CHECKLIST.md`.

### 6. Optional, only if time remains: the trained-classifier baseline

As scoped in "Answering the model-training-speed question" above. Treat as a bonus
that strengthens an already-covered pillar, not a blocker for submission.

### 7. Submission package (slides, video, README)

Per the hackathon brief's four submission requirements: public GitHub repo link,
deployed-tool link, 4-6 slide deck, short video pitch. Build this only after step 5,
so the deck can cite the real eval numbers and limitations instead of being written
around a gap that later needs patching.

## Explicitly out of scope for this sprint

- Any new conversational specialist, workflow, or product domain beyond
  Account/Transaction/disputes (per the hackathon brief: "implementing more
  workflows does not earn an automatic bonus").
- Rebuilding a transaction/entity matcher, analyst console UI, or cloud
  orchestration migration (see "Interesting but not worth adopting" in
  [REFERENCE_PATTERNS.md](REFERENCE_PATTERNS.md)).
- Automatic UI polling was deferred in the original sprint but is now implemented
  and locally tested. Browser verification remains open; see
  [the browser acceptance issue #56](https://github.com/cristofima/factored-hackathon-2026-cristopher-coronado/issues/56).
