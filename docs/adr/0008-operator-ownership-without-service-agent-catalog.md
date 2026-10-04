# ADR 0008: Operator Ownership Without a ServiceAgent Catalog

| Status   | Date       | Proposed by | Approved by | Supersedes                                                                                                               |
| -------- | ---------- | ----------- | ----------- | ------------------------------------------------------------------------------------------------------------------------ |
| Accepted | 2026-10-03 | cristofima  | cristofima  | [0007](0007-real-operator-exclusive-dispute-takeover.md) (catalog retention only; exclusive takeover authority retained) |

---

## Context

The active case workflow handles suspected transaction fraud. The inherited
`ServiceAgent` catalog contains simulated reviewers and unrelated specialties,
whereas Identity owns real authenticated operators. Keeping both concepts for
case responsibility obscures who accepted a review and adds catalog ingestion
and relationship maintenance without an operational purpose. Historical
assignments must remain explainable without being mistaken for real ownership.

## Decision

Use the stable Identity operator identifier for nullable case ownership. Taking a
case records its owner, claim timestamp, version and audit event atomically, under
the exclusive authority established in ADR 0007. An unclaimed or historically
simulated assignment never becomes real operator ownership through backfill.

Retire the optional Operator-to-ServiceAgent association and the active
ServiceAgent catalog, including runtime dependencies and catalog loading.
Preserve legacy assignment metadata in durable historical snapshots or archival
records before removing its foreign keys or source table. Existing audit text is
not rewritten. Identity remains responsible for authenticating and revalidating
operators; a persisted association alone never grants authority.

Risk classifications remain case evidence rather than reviewer entities. Cases
concern possible fraud, not confirmed fraud. This migration does not add verdicts,
reassignment, automated closure or financial effects.

## Alternatives Considered

- Keep the shared catalog indefinitely: rejected because historical preservation
  does not require maintaining an active simulated staff model.
- Convert simulated reviewers into operators: rejected because catalog rows do
  not prove a real authenticated identity or acceptance of responsibility.
- Drop legacy assignments without preservation: rejected because it destroys
  historical attribution and prevents explaining old audit records.

## Consequences

Case responsibility has one operational representation, and operators no longer
carry an unrelated optional catalog association. Catalog ingestion and live
contracts become smaller.

Removing a table requires coordinated schema, loader, API and deployment changes.
Historical snapshots retain audit context but cannot authenticate a reviewer.
Migration tests and offline checks do not establish that a live PostgreSQL
migration, concurrent claims or deployed identity transport have succeeded.
Those runtime checks remain separately authorized acceptance gates.
