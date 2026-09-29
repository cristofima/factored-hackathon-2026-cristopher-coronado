# Banking Web Frontend

React and Vite frontend for the Banking Assistant prototype. The assistant uses the local or deployed Responses BFF and does not call Foundry directly.

## Local Development

```powershell
cd app/frontend/banking-web
npm install
npm run dev
```

Vite normally listens at `http://localhost:5170`. The root `DEV - Full Stack Ordered` VS Code launch starts Account MCP (`8070`), Transaction MCP (`8071`), the local Responses agent (`8088`), the BFF (`8080`), and this frontend.

The Vite proxy routes:

| Route                 | Local target            |
| --------------------- | ----------------------- |
| `/api/accounts/*`     | `http://localhost:8070` |
| `/api/transactions/*` | `http://localhost:8071` |
| `/responses`          | `http://localhost:8080` |
| `/auth/*`             | `http://localhost:8080` |

## Environment

| Variable                   | Purpose                                         | Local default                     |
| -------------------------- | ----------------------------------------------- | --------------------------------- |
| `VITE_BACKEND_URI`         | Fallback base for relative REST calls           | `/api` in code                    |
| `VITE_ACCOUNT_API_URL`     | Deployed Account API base, including `/api`     | Falls back to `VITE_BACKEND_URI`  |
| `VITE_TRANSACTION_API_URL` | Deployed Transaction API base, including `/api` | Falls back to `VITE_BACKEND_URI`  |
| `VITE_RESPONSES_API_URL`   | Responses BFF endpoint                          | `/responses` in code              |
| `VITE_RESPONSES_BFF_URL`   | BFF base URL for login, profile, and accounts   | Empty; same-origin `/auth` routes |

The frontend signs in through the [Responses BFF](../../responses-bff/README.md) at `/auth/login`, keeps the short-lived application JWT in browser storage, and restores verified identity through `/auth/me`. The BFF verifies PostgreSQL-backed Argon2 users and returns the persisted customer name. Navigation uses that name, with an email fallback. The frontend does not create users, fixed bearer tokens, or synthetic profiles.

## Account Page

The Account page calls `/auth/me/accounts` with the application JWT. The BFF selects only
savings and checking products owned by the verified user/customer association. One account
is displayed directly; multiple accounts expose a selector with the type and masked number
(product ID fallback). Loading, retryable errors, and no-account states are explicit.

The holder comes from the authenticated profile. Type, status, opening date, currency,
and account number come from PostgreSQL; absent values are not fabricated. The Account
Codes section appears only when a stored number exists. SWIFT, IBAN, and routing numbers
are omitted because the schema does not provide them. Agreements and Privacy & Security
Policy are unchanged inherited placeholders. Credit-card management is unavailable in
this prototype and does not execute simulated card operations.

## Validation

```powershell
npm run lint
npm run build
```

The current assistant supports Account and Transaction inquiries plus generic approval events. Payment submission and attachment upload are not active features.
