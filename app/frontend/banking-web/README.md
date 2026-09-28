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

## Environment

| Variable                   | Purpose                                         | Local default                    |
| -------------------------- | ----------------------------------------------- | -------------------------------- |
| `VITE_BACKEND_URI`         | Fallback base for relative REST calls           | `/api` in code                   |
| `VITE_ACCOUNT_API_URL`     | Deployed Account API base, including `/api`     | Falls back to `VITE_BACKEND_URI` |
| `VITE_TRANSACTION_API_URL` | Deployed Transaction API base, including `/api` | Falls back to `VITE_BACKEND_URI` |
| `VITE_RESPONSES_API_URL`   | Responses BFF endpoint                          | `/responses` in code             |

The frontend signs in through the BFF at `/auth/login`, keeps the short-lived application JWT in browser storage, and restores verified identity through `/auth/me`. The BFF currently verifies environment-configured Argon2 users; PostgreSQL-backed user persistence remains pending. The frontend does not create users, fixed bearer tokens, or synthetic profiles.

## Validation

```powershell
npm run lint
npm run build
```

The current assistant supports Account and Transaction inquiries plus generic approval events. Payment submission and attachment upload are not active features.
