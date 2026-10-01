# ADR 0003: PostgreSQL as the operational data store for the live tool-calling path

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-09-28 | cristofima  | cristofima  |

---

## Context

The forked sample repository originally served Account and Transaction data from
in-memory sample fixtures. A real backing store was needed to demonstrate the
rubric's data-engineering rigor (contracts, quality checks, lineage, update
policy). Microsoft's own guidance on AI agent tool design recommends governed,
parameterized tools (SQL MCP Server / Data API builder style) over an analytical
warehouse for predictable, permission-bound point lookups by customer, account, or
product id, which is exactly this workflow's access pattern; it recommends
Fabric/Synapse with NL2SQL instead for open-ended natural-language analytics
questions, which is not the live tool-calling path here.

## Decision

Azure Database for PostgreSQL Flexible Server is the operational store backing
every live agent tool and REST endpoint, accessed through a shared `banking_shared`
SQLModel package (SQLAlchemy 2.0 + Pydantic), never raw SQL strings. One SQLModel
class serves as both the database table definition and the API/tool schema.
Fabric/Synapse with pandas/DuckDB is reserved only for the offline Phase 4
data-backed baseline analysis, run locally against a filtered subset of the
supplied CSVs, never for the live path.

## Consequences

Easier: a single schema definition is reused by Account, Transaction, and the data
ingestion pipeline instead of maintaining parallel definitions; customer-ownership
authorization becomes an ordinary parameterized query the service layer can test
directly. Harder: every schema change now requires Alembic migration discipline
across all three consumers (Account, Transaction, data pipeline), and the shared
package version must stay in lockstep across services or they silently drift apart.

## Related

- [0002](0002-deterministic-fraud-score-triage-over-trained-model.md) depends on
  `fraud_score`/`is_fraud` being persisted in this store.
- [0004](0004-custom-jwt-authentication-over-entra-id.md) depends on this store
  for the persisted, Argon2-hashed user records it authenticates.
