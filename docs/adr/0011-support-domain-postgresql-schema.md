# ADR 0011: One PostgreSQL Schema for the Support Domain

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-10-05 | cristofima  | cristofima  |

---

## Context

Support cases, audit events, recorded financial effects and case-specific card
protection form one operational domain. Adding conversation evidence creates
another related table. The owner requested one `support` schema and consolidation
through the unpublished conversation-history migration.

## Decision

Place `support_cases`, `support_case_events`, `runtime_postings`, `card_protections`
and `case_conversations` in PostgreSQL schema `support`. Keep banking and Identity
tables in `public`. Canonical Shared SQLModel metadata owns these declarations;
internal support foreign keys are schema-qualified. Do not change global search path.

Use one unpublished migration to create the schema, move existing tables preserving
records and constraints, and create conversation evidence. Limit Alembic reflection
to canonical managed tables, excluding unrelated or retained withdrawn objects.

## Alternatives considered

- Leave all tables in `public`: does not satisfy the approved domain separation.
- Separate schemas for cases, effects and evidence: fragments one support domain
  without a current ownership requirement.
- Recreate existing tables: introduces unnecessary data-copy and integrity risks
  compared with PostgreSQL table movement.

## Consequences

The schema expresses domain ownership without a new datastore or service boundary.
Existing case and financial-effect relationships remain intact; schema-qualified
metadata and schema-aware fixtures are required.

Source migration lineage does not authorize recovery of an applied withdrawn
revision. Migration-marker correction and removal of retained objects require
separate authorization. Destructive downgrade requires explicit evidence-retention
review; offline compilation is not proof of successful live migration. Environment
execution evidence belongs in the [Data guide](../../app/business-api/data/README.md#schema-and-ownership),
not in the schema decision.
