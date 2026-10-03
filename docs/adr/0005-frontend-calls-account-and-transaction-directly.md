# ADR 0005: Frontend calls Account and Transaction directly; BFF trimmed to identity and agent proxy

| Status     | Date       | Proposed by | Approved by | Superseded by                                                                                       |
| ---------- | ---------- | ----------- | ----------- | --------------------------------------------------------------------------------------------------- |
| Superseded | 2026-10-01 | cristofima  | cristofima  | [0006-dedicated-auth-users-and-staff-identities](0006-dedicated-auth-users-and-staff-identities.md) |

---

## Context

The Responses BFF originally fronted every browser-facing read, including
financial data (`bff/accounts.py` exposing `/auth/me/accounts`, `/auth/me/cards`,
`/accounts/{product_number}/transactions`), in addition to its identity and
Responses-proxy responsibilities. This duplicated Account's and Transaction's own
data access and customer-ownership authorization logic in a second place, added a
network hop for every financial read, and created two locations where an
authorization check could independently drift out of sync.

## Decision

As of this date, the browser calls Account and Transaction directly over REST
(`GET /accounts`, `GET /cards`, `GET /{product_number}/history`,
`/api/support-cases`), authenticated with the same application JWT the BFF issues,
each service independently verifying it through its own `jwt_identity.py`
dependency. The BFF's financial-read endpoints and `bff/accounts.py` are deleted;
the BFF's scope is reduced to `/auth/login`, `/auth/me`, and fronting the Responses
agent stream only. `CORS_ALLOWED_ORIGINS`-driven `CORSMiddleware` is enabled
directly on Account and Transaction to support this.

## Consequences

Easier: exactly one authorization implementation per resource, inside that
service's own `services.py`, instead of a second copy living in the BFF; fewer
network hops for every financial read; the BFF's audit surface shrinks to identity
and chat-proxying only, which is easier to reason about and review. Harder: the
JWT secret, issuer, and audience must now stay in sync across three independently
deployed services (BFF, Account, Transaction) instead of one, and CORS
configuration must be correct on two additional services rather than centralized
behind a single BFF origin.

## Related

- [0004](0004-custom-jwt-authentication-over-entra-id.md) is the authentication
  mechanism this ADR reuses for the browser's direct calls.
