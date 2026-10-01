# ADR 0002: Deterministic fraud_score threshold triage instead of training a new fraud-detection model

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-10-01 | cristofima  | cristofima  |

---

## Context

The transaction-dispute support case needs to decide, for each opened case, whether
to fast-track a resolution or escalate to a simulated human reviewer. The initial
assumption was that the supplied dataset lacked the signals real bank dispute
investigations rely on (device/IP/geolocation, risk scoring) and that building
genuine fraud detection would require fine-tuning a model. That assumption turned
out to be wrong: the raw source CSVs already carry `transaction_country`,
`transaction_city`, `response_code`, `is_fraud`, and `fraud_score` for every
customer back to 2023 — simply never mapped into the persisted Postgres schema. The
hackathon rubric requires evaluating at least one learned component against a
baseline, but explicitly allows this to be demonstrated through "component
selection, relevance or intent labels, representations, leakage prevention, held-out
evaluation, and error analysis" rather than only through training a new model.

## Decision

Use the dataset's precomputed `fraud_score` as a deterministic triage threshold
(`fraud_score >= 32`) inside `dispute_service.py`, tuned and evaluated offline
against the dataset's own `is_fraud` label
(`scripts/evaluate_fraud_threshold.py`, run over the full raw 4.4M-row transaction
history: precision 1.0, recall 0.668, F1 0.801, zero false positives in-sample).
`is_fraud` is used only for this offline evaluation and is never surfaced to the
agent or used as a live signal; `fraud_score` is framed honestly as a value the
bank's own existing fraud engine already assigned at authorization time, not
something the agent invents or infers.

## Consequences

Easier: no model-training or model-serving pipeline to build, version, or monitor
under a ten-day deadline; the triage rule is a single auditable line, fully
reproducible from the evaluation script's output. Faster to ship, and matches every
other reviewed competitor building the same track, none of whom trained a
from-scratch fraud model either. Harder: roughly a third of labeled-fraud rows in
the dataset fall below this threshold and are not caught by the score alone
(mitigated only by also escalating transactions with a missing `fraud_score`); the
submission materials must explicitly justify why a tuned, evaluated threshold
counts as the rubric's required "learned component vs. baseline" evidence, since a
grader skimming quickly could otherwise expect a trained classifier specifically.

## Related

- [0001](0001-single-workflow-scope-with-dispute-support-case.md) is the parent
  decision: this threshold only exists because that ADR scoped a dispute
  support-case layer that needs a triage rule.
- [0003](0003-postgresql-as-the-operational-data-store.md) is where `fraud_score`
  and `is_fraud` are persisted and queried from for this threshold.
