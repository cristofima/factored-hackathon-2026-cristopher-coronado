# Responses BFF

FastAPI browser trust boundary for the banking assistant. It authenticates PostgreSQL
users, returns persisted customer profiles, bank accounts, and credit/debit cards, and proxies Responses
streams to the local agent or Foundry. The browser never receives Azure credentials.

## Request Flow

```mermaid
flowchart LR
    Browser[Banking web] -->|Application JWT| BFF[Responses BFF]
    BFF -->|SQLModel| DB[(PostgreSQL)]
    BFF -->|Signed verified identity| Agent[Responses agent]
    Agent -->|Short-lived bearer| MCP[Account and Transaction MCP]
```

Profile, account, card, Dashboard, and Analytics reads use PostgreSQL directly from the BFF. Conversational
inquiries use the agent and MCP services; the BFF read endpoint does not replace their
service-layer ownership checks.

## HTTP Contract

| Method | Route                                 | Behavior                                                                                           |
| ------ | ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| POST   | `/auth/login`                         | Verify persisted email and Argon2 password hash; return bearer token and user profile.             |
| GET    | `/auth/me`                            | Return verified identity and persisted customer name. Requires bearer JWT.                         |
| GET    | `/auth/me/accounts`                   | Return owned savings and checking accounts. Requires bearer JWT.                                   |
| GET    | `/auth/me/cards`                      | Return owned credit and debit cards with masked numbers. Requires bearer JWT.                      |
| GET    | `/accounts/{account_id}/transactions` | Return an owned bank account's transactions with date filters and pagination. Requires bearer JWT. |
| POST   | `/responses`                          | Proxy Responses events with verified identity and user-bound conversations. Requires bearer JWT.   |

JWT identity includes `sub`, `customer_id`, `email`, and `locale`, with `iss`, `aud`,
`iat`, and `exp` metadata. The display `name` is profile response data, not a JWT claim.
Missing customer names return `null`.

Account summaries contain `id`, `type`, nullable `status`, nullable `opened` (ISO date),
nullable `number`, `currency`, and nullable decimal-string `balance`. The balance is
the stored current value, not a historical balance for a transaction window.
Queries verify the persisted user/customer association,
filter `Cuenta Ahorro` and `Cuenta Corriente`, and order by product ID. The endpoint
does not accept a customer identifier to select another customer's accounts. No accounts
returns an empty array; database/configuration failures return a safe `503` response.
Missing or invalid bearer credentials return `401`.

### Cards

`GET /auth/me/cards` returns products of type `Tarjeta Crédito` and `Tarjeta Débito`,
ordered by product ID. The query verifies both the authenticated `sub` and
`customer_id` against the persisted user/customer association. It lists customer-owned
cards without inferring a relationship to a particular bank account; bank-account
and transaction endpoints remain restricted to savings and checking products.

Card summaries contain the account-summary fields plus nullable `expires` (ISO date)
and nullable decimal-string `credit_limit`. Numbers are masked server-side as
`****` followed by the last four characters. Missing numbers, dates, balances, and
limits remain `null`. Stored balance and limit are returned without calculating
available credit or utilization. No matching cards returns an empty array; missing
or invalid credentials return `401`, and database/configuration failures return `503`.
Payments, recharge, blocking, and limit changes are not implemented by this endpoint.

### Transactions

`GET /accounts/{account_id}/transactions` accepts optional ISO calendar dates
`start_date` and `end_date` (inclusive), `limit` from 1 to 100 (default 100), and
nonnegative `offset` (default 0). Invalid parameters or a reversed date window
return `422`. Foreign, missing, or non-bank products return the same `404` response;
database/configuration failures return a safe `503`.

The response contains `items`, `total`, `limit`, `offset`, `start_date`, and `end_date`.
Each item includes `id`, `account_id`, `date`, decimal-string `amount`, `currency`,
and nullable `type`, `category`, `channel`, `merchant`, and `status`. Results are
ordered by transaction date and ID descending. An owned account with no matching
transactions returns an empty `items` array and zero `total`.

Ownership is checked against the persisted user/customer/product association before
reading transactions. Clients must fetch every page before computing window totals.
Pagination is not a cross-request database snapshot; concurrent changes may require
a refresh. Date bounds currently use naive datetimes against timezone-aware columns;
timezone-independent boundary behavior remains an open validation condition.

## Local Development

Run from the repository root using the ignored root `.env.dev`:

```powershell
uv sync --project app/responses-bff
uv run --project app/responses-bff --env-file .env.dev uvicorn bff.main:app --app-dir app/responses-bff --port 8080
```

Set `PROFILE=dev`, `RESPONSES_UPSTREAM_MODE=local`, and
`RESPONSES_AGENT_ENDPOINT=http://127.0.0.1:8088/responses` in that environment.
The root `DEV - Full Stack Ordered` launch starts this service with the MCP services,
agent, and frontend. Restart the BFF after Python edits when running without `--reload`.

## Configuration

| Variable                   | Purpose / default                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`             | Shared SQLModel PostgreSQL connection URL; required for persisted login/profile/account reads.    |
| `JWT_SECRET_KEY`           | Application HS256 signing key, at least 32 characters.                                            |
| `JWT_ISSUER`               | `home-banking-api`                                                                                |
| `JWT_AUDIENCE`             | `home-banking-web`                                                                                |
| `JWT_ACCESS_TOKEN_MINUTES` | `15`; supported range `1` to `60`.                                                                |
| `INTERNAL_IDENTITY_SECRET` | Shared downstream identity signing secret, at least 32 characters.                                |
| `RESPONSES_UPSTREAM_MODE`  | `foundry` by default; use `local` for local browser validation.                                   |
| `RESPONSES_AGENT_ENDPOINT` | Local default `http://127.0.0.1:8088/responses`; configure the approved upstream for hosted mode. |
| `RESPONSES_TOKEN_SCOPE`    | `https://ai.azure.com/.default`                                                                   |
| `AZURE_CLIENT_ID`          | Optional client ID for server-side Azure credentials.                                             |
| `ALLOWED_ORIGINS`          | JSON array; defaults to `["http://localhost:5170"]`.                                              |

Keep secrets in ignored environment files or protected deployment settings. Never log
passwords, password hashes, JWTs, or Azure credentials. `AUTH_USERS` is not a login
source. Seed demo identities separately using the [data module guide](../business-api/data/README.md#seed-demo-users).
The shared models and session factory live in [banking-shared](../business-api/shared).

## Validation and Limits

```powershell
cd app/responses-bff
uv run python -m pytest tests -q
```

Tests cover persisted repository queries, authentication, profile/account responses,
transaction date filters and pagination, ownership filtering, and Responses proxy
behavior. Card contract tests cover credit/debit filtering, masked numbers, decimal
precision, null fields, cross-user isolation, invalid credentials, and unavailable
database responses. The focused account/card suite passed with 36 tests, and the
user confirmed that credit and debit cards appear in the local frontend. This does
not establish a complete two-user card browser/error matrix or deployed parity.
Local PostgreSQL comparisons and desktop browser login, balances, and
transaction rows passed for two approved users. Simulated transaction failures and
rejected sessions exercised UI recovery; natural JWT expiration remains unverified.

This is not evidence of complete conversational parity. The agent profile provider
still injects a sample email, and a local account inquiry was correctly denied by
service ownership checks. Beneficiaries has no persisted source. Hosted identity
transport and deployed parity still require separate validation.
Registration, password reset, MFA, revocation, and
production identity lifecycle controls are not implemented.

For zip packaging and dependency export, follow the
[root deployment artifact guide](../../README.md#python-dependency-artifact-for-app-service-zip-deploy).
