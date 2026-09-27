# Banking Web Frontend (React + Vite)

Frontend app for the Banking Assistant prototype.

## What this app does

- Renders the banking UI pages (dashboard, payments, cards, analytics).
- Embeds the ChatKit-based assistant UI.
- Calls backend business APIs through `/api/*` routes.
- Streams assistant responses through `/chatkit`.

## Tech stack

- React 18 + TypeScript
- Vite 5
- Tailwind CSS + shadcn/ui
- TanStack Query

## Prerequisites

- Node.js 18+ (recommended: latest LTS)
- npm

## Package manager

This frontend is standardized on npm. Use `npm install` and `npm run <script>`.

## Install

```powershell
cd app/frontend/banking-web
npm install
```

## Run locally

```powershell
cd app/frontend/banking-web
npm run dev
```

Default dev URL: `http://localhost:5170`. If Vite selects another available port, use the URL printed in its terminal.

In VS Code, `DEV - Full Stack Ordered` starts the services and opens this frontend on port `5170`. Keep that port free when using `F5`; when running Vite manually, use the URL printed in its terminal if it selects another port.

## Build and preview

```powershell
npm run build
npm run preview
```

## Environment variables

This app reads the following Vite variables (`import.meta.env`):

| Variable                      | Purpose                                                                      | Default in code                                  |
| ----------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------ |
| `VITE_BACKEND_URI`            | Base URL for REST calls used by `BFFClient` (`/api/...` paths are appended). | `""` (empty string), so requests remain relative |
| `VITE_CHATKIT_API_URL`        | ChatKit API URL used by shared config.                                       | `/chatkit`                                       |
| `VITE_CHATKIT_API_DOMAIN_KEY` | Domain key consumed by ChatKit config.                                       | `domain_pk_localhost_dev`                        |
| `VITE_CHAT_SERVER_URL`        | Chat server URL used by chat pages/components.                               | `/chatkit`                                       |

Env templates already included in this folder:

- `.env.example`: committed template for the team.
- `.env.local`: local defaults for this workspace.

If needed, create/update your local env file:

```powershell
# app/frontend/banking-web/.env.local
VITE_BACKEND_URI=
VITE_CHAT_SERVER_URL=/chatkit
VITE_CHATKIT_API_URL=/chatkit
VITE_CHATKIT_API_DOMAIN_KEY=domain_pk_localhost_dev
```

Notes:

- With `VITE_BACKEND_URI` empty, requests are relative and go through Vite dev proxy.
- Set `VITE_BACKEND_URI` only if you want to bypass proxy and call a remote backend directly.

## Dev proxy setup (Vite)

`vite.config.ts` proxies local routes to services:

- `/api/accounts/*` -> `http://localhost:8070`
- `/api/transactions/*` -> `http://localhost:8071`
- `/chatkit` -> `http://localhost:8080`
- `/upload` -> `http://localhost:8080`
- `/preview` -> `http://localhost:8080`

To run end-to-end locally, make sure these backend services are running:

- Account MCP on `8070`
- Transaction MCP on `8071`
- Payment MCP on `8072` for payment requests
- Backend ChatKit server on `8080`

## Verified chat path

On 2026-09-26, a local browser `threads.create` request to `/chatkit` streamed a transaction-history inquiry. The UI showed handoff to `TransactionHistoryAgent`, successful account and recipient-transaction lookups, a table of Contoso payments, and a final answer. Azure OpenAI returned HTTP 200 for the chat completions in this run. This verifies the account/transaction inquiry in the local UI; payment execution, login/authorization, and hosted deployment were not part of this check.

## Scripts

- `npm run dev`: start dev server
- `npm run build`: production build
- `npm run build:dev`: build in development mode
- `npm run lint`: run ESLint
- `npm run preview`: preview production build

## Common issues

- Blank or failing chat requests:
  - Check backend chat server is up on `8080`.
  - Check `VITE_CHAT_SERVER_URL`/`VITE_CHATKIT_API_URL` values.
- REST calls fail with 404/connection errors:
  - Verify account (`8070`) and transaction (`8071`) services are running.
  - If using `VITE_BACKEND_URI`, ensure the remote URL exposes `/api/accounts` and `/api/transactions`.
- CORS issues:
  - Prefer relative URLs + Vite proxy during local development.
