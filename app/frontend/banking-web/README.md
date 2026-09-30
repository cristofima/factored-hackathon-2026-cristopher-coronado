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

| Route         | Local target            |
| ------------- | ----------------------- |
| `/accounts/*` | `http://localhost:8080` |
| `/responses`  | `http://localhost:8080` |
| `/auth/*`     | `http://localhost:8080` |

## Environment

| Variable                 | Purpose                                                            | Local default             |
| ------------------------ | ------------------------------------------------------------------ | ------------------------- |
| `VITE_RESPONSES_API_URL` | Responses BFF endpoint                                             | `/responses` in code      |
| `VITE_RESPONSES_BFF_URL` | BFF base URL for authentication, accounts, cards, and transactions | Empty; same-origin routes |

Active browser reads do not call Account or Transaction MCP services directly.
Legacy REST client modules remain in the source tree, but are not used by the
in-scope financial screens and have no direct-service Vite proxy.

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
Policy are unchanged inherited placeholders.

Account uses a stable two-column desktop layout, compact panels, and aligned
label/value rows. Account Codes keeps its position when present; missing codes
do not cause the agreements and policy panels to change columns.

## Credit and Debit Cards

The [card page](src/pages/CreditCardManagement.tsx) at `/credit-cards` reads
`/auth/me/cards` through the authenticated BFF. It displays the verified customer's
credit and debit products, not cards inferred from the selected bank account.
Each card has a separate read-only panel with its stored type, masked number, product
ID, and status, followed by a prominent balance, a separate credit limit, and opening
and expiration dates. Amounts include their currency and thousands separators without
converting decimal strings to floating-point numbers. Card numbers are masked by the BFF before reaching
the browser. Nullable fields display `Not available`; decimal strings are preserved
without estimating debt, available credit, or utilization.

The card grid retains empty column tracks: one card has the same width as each
card in a two-card desktop layout rather than expanding across the entire row.

Loading, no-card, error, retry, and rejected-session messages are explicit. User
changes and retries clear previous rows and abort old requests. A `401` message
asks the user to sign in again but does not itself clear the authentication context.
The page is read-only: payments, recharge, blocking, and limit changes remain
unavailable, with no simulated operations or financial fallback.

## Dashboard and Analytics

Both screens use [FinancialOverview](src/components/FinancialOverview.tsx) with
authenticated BFF reads. Account selection uses `/auth/me/accounts`; transactions
use `/accounts/{account_id}/transactions`. The default date window covers today
and the preceding 29 calendar days. The Analytics link carries the selected account
and inclusive date window; an account URL parameter must match an owned account.

The [financial client](src/api/financialClient.ts) fetches all pages in batches of
100 before exposing records. It rejects changing totals, duplicate IDs, foreign
account records, and incomplete pagination rather than falling back to fixtures.
Account/window changes abort old requests and clear previous rows. Dashboard shows
up to five records; Analytics shows the complete fetched window.

The shared view uses aligned account/date controls, a compact current-balance
panel, and right-aligned tabular transaction amounts. These presentation changes
do not alter date filters, pagination, precision, or movement classifications.

Balances are stored current balances, not balances reconstructed for the selected
window. Transaction dates display the calendar date returned by the service without
browser timezone conversion. Missing fields remain unavailable. Loading, empty,
invalid-window, failure, retry, and rejected-session messages are explicit; a
financial `401` message does not itself clear the authentication context.

Analytics derives movement totals with exact four-decimal arithmetic, separately
for each currency. Only `Approved` records qualify: `Deposit` is inflow, while
`Payment`, `Purchase`, `Transfer`, and `Withdrawal` are outflow. Adjustments, unknown
types, other statuses, and negative amounts are excluded and counted. These are
dataset-policy movements, not income/spending classifications or historical balances.
No mixed-currency total or estimated monthly snapshot is displayed.

Dashboard and Analytics have no mock financial fallback. Payments, investments,
beneficiaries, and card mutations remain unavailable rather than simulating data
or operations. Support-case workflows are not implemented by this slice.

## Validation

```powershell
npm test
npm run lint
npm run build
```

Financial arithmetic and pagination tests passed (19 tests), as did the frontend
build and focused financial lint. Global lint still reports unrelated existing
errors in WidgetRenderer, two UI components, and Tailwind configuration.

The card page compiled successfully, and the user confirmed local credit/debit card
display. The BFF account/card contract suite passed with 36 tests, including masking
and ownership cases. Card-specific browser recovery and complete two-user parity
have not yet been recorded. The user supplied desktop screenshots of the card panels
and Dashboard. Subsequent card-grid, Account, and Dashboard presentation changes
passed build and focused lint; the 19 frontend tests passed again. The latest layout
has not been independently inspected in an authenticated browser session. Account
retains inherited placeholder-link accessibility diagnostics; global lint is not clean.

Desktop browser balances and transaction rows matched authenticated BFF reads for
two approved users; PostgreSQL comparisons were performed separately. Transaction
`503` and `401` UI states were simulated. Natural session expiration, normal pointer
interaction, and the complete signed agent/MCP matrix remain open. Mobile responsive
validation is deferred.

The assistant uses the verified email from signed BFF identity for Account and
Transaction inquiries, with generic approval-event support. User-supplied local
browser evidence on 2026-09-30 shows an owned-account answer with a full bank number
and masked card number, and a foreign-account denial rendered after `ACCESS_DENIED`.
The reported blank chat response is resolved for these cases; Transaction chat,
missing/empty results, multi-turn and approval continuation remain separate checks.

Threads, messages, and the returned conversation identifier live in React state.
Reloading clears them: the next message creates a new conversation even if the
login JWT is still valid. Later messages in the same thread reuse the identifier.
Hosted identity transport and deployed financial parity are not verified. See the
[real-data gate](../../../DEMO_SCOPE_CHECKLIST.md#0-real-data-verification-gate-next)
before starting support cases. Payment submission and attachment upload are not active features.
