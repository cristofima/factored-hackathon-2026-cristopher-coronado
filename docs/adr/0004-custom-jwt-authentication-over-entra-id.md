# ADR 0004: Custom email/password JWT authentication instead of Microsoft Entra ID

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-09-28 | cristofima  | cristofima  |

---

## Context

The hackathon brief requires "a trusted test session or identity service"; it does
not mandate a specific identity provider, and explicitly states "a national ID or
customer number alone does not prove identity." A single developer with a ten-day
window had to choose an identity mechanism that satisfies that bar without
consuming days of Entra ID app registration, tenant configuration, and MSAL
client wiring that would not move any rubric dimension for this prototype.

## Decision

Implement custom email/password authentication: Argon2 password hashing, short-lived
HS256 JWTs carrying `sub`, `customer_id`, `email`, `locale`, `iss`, `aud`, and `exp`,
issued by the Responses BFF after verifying PostgreSQL-backed users. Account and
Transaction independently re-verify that same JWT (same secret/issuer/audience) for
their own direct REST endpoints via `jwt_identity.py`, separate from the
agent-only, 60-second internal bearer (`internal_identity.py`) used for MCP tool
calls.

## Consequences

Easier: no external identity provider dependency for local development or grading;
demo users and their Argon2 hashes are seeded directly into PostgreSQL outside
source control. Harder: the custom auth stack (hashing, token issuance, secret
rotation, expiration handling) is the team's own responsibility rather than
delegated to a managed identity platform; a production deployment would still need
to migrate to a managed identity provider, which is explicitly out of scope for
this prototype and must be stated as remaining work in the submission, not implied
as already solved.

## Related

- [0003](0003-postgresql-as-the-operational-data-store.md) is where the users this
  ADR authenticates are persisted.
- [0005](0005-frontend-calls-account-and-transaction-directly.md) depends on this
  same application JWT to authenticate the browser's direct calls to Account and
  Transaction.
