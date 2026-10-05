# ADR 0010: Bounded Customer-Provided Case Conversation Evidence

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-10-05 | cristofima  | cristofima  |

---

## Context

Charge-recognition assistance and pre-intake discussion explain why a customer
submits a dispute, but provider conversation retention does not make that context
available through customer or operator case pages. Local and hosted provider
continuation must remain independent from application case evidence. The owner
approved persisted case history and explicitly excluded Cosmos export.

## Decision

Persist an immutable, bounded snapshot of customer-provided visible user/assistant
messages in PostgreSQL when the customer explicitly accepts intake. Persist it in
the same transaction as the case, consent and routing. Exclude system/tool messages,
hidden reasoning and credential state. Label its provenance `CUSTOMER_PROVIDED`:
it is contextual evidence, not an authoritative provider transcript.

Only the owning customer and exact assigned operator may retrieve it. Authorized
legacy or direct cases may have no transcript. Recovery never replaces the snapshot.
Provider continuation remains BFF-owned and does not depend on this snapshot.

## Alternatives considered

- Provider traces alone: retained provider state does not establish case association
  or application-level customer/operator access.
- Cosmos conversation export: excluded by the owner and introduces another store.
- Mutable complete chat archive: expands retention and trust scope beyond the
  approved bounded intake evidence.

## Consequences

Customer and operator views can share pre-intake context without coupling case
availability to provider retention. Atomic capture avoids orphan evidence.

The client supplies the transcript, so omissions or altered text are possible;
operators must not treat it as verified provider history. A submitted snapshot may
omit earlier discussion, but invalid or oversized submissions are rejected, never
silently truncated. Cases created without capture remain empty. Retention/deletion policy
needs separate approval before destructive cleanup. Offline tests do not establish
browser, hosted transport or persisted-data acceptance.
