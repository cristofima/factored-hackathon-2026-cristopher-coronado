# ADR 0007: Real Operator Exclusive Dispute Takeover

| Status                                                                                                     | Date       | Proposed by | Approved by | Supersedes                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------- | ---------- | ----------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Accepted; catalog retention superseded by [0008](0008-operator-ownership-without-service-agent-catalog.md) | 2026-10-03 | cristofima  | cristofima  | [0002](0002-deterministic-fraud-score-triage-over-trained-model.md) (simulated reviewer assignment only; deterministic score routing retained) |

---

## Context

Customer approval starts a dispute review, but a randomly selected `ServiceAgent`
catalog entry does not identify an authenticated person responsible for the case.
Independent operator identities now exist through [ADR 0006](0006-dedicated-auth-users-and-staff-identities.md).
The user approved real operator takeover while explicitly separating ownership
from final-verdict authority. Multiple operators may try to take the same case;
application-level read-then-write checks cannot establish exclusive ownership.

## Decision

Active Identity operators may view the consented `IN_REVIEW` queue and take an
unowned case through a separate operator REST surface. Every protected request
revalidates the current Identity role, lifecycle and version. Customer, admin and
agent identities cannot substitute for an operator.

Claiming conditionally updates the persisted case and records the authenticated
operator subject, claim time, case version and audit event in one transaction.
Only one competing claim may succeed; rejected claims expose a controlled conflict,
not another operator's credentials or internal errors. Detail access is limited
to the permitted queue/ownership scope.

New reviews do not assign simulated `ServiceAgent` entries as human responsibility.
The shared catalog and historical metadata remain intact. The existing score
threshold still classifies routing priority; a missing score is never inferred.
Customer consent, eligibility and customer-owned read boundaries remain unchanged.

Taking a case grants responsibility only. This decision does not authorize
reassignment, operator adjudication, automatic closure, refunds, balance changes
or product blocking. Existing explicit customer-authorized resolution is not
silently converted into an operator verdict contract.

## Alternatives Considered

- Keep random catalog assignment: rejected because it cannot establish who
  actually accepted responsibility or enforce authenticated ownership.
- Treat every staff role as a reviewer: rejected because administration and case
  responsibility are distinct authorities.
- Add adjudication and financial effects together with takeover: deferred because
  evidence requirements, decision authority, idempotency and settlement policy
  need separate approval.

## Consequences

Ownership becomes attributable and competing requests have a database-enforced
winner. Operator routes and UI remain independent from customer chat and do not
introduce another conversational specialist.

The additional schema and API require coordinated migration and deployment.
Identity outages fail closed. Unit tests, including SQLite claim tests, do not
establish PostgreSQL concurrency, deployed migrations or browser acceptance.
Those checks need separately authorized runtime validation. Claim abandonment,
reassignment and final verdicts remain explicit future policy decisions; takeover
alone does not complete an investigation.
