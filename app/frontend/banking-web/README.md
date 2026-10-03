# Banking Web Frontend

React and Vite frontend for the Banking Assistant prototype. The assistant uses the local or deployed Responses BFF and does not call Foundry directly.

## Local Development

```powershell
cd app/frontend/banking-web
npm install
npm run dev
```

Node runtime baseline is `>=22` (aligned with `package.json` engines and frontend CI defaults).

Vite normally listens at `http://localhost:5170`. The root `DEV - Full Stack Ordered` VS Code launch starts Identity (`8090`), Account MCP (`8070`), Transaction MCP (`8071`), the local Responses agent (`8088`), the BFF (`8080`), and this frontend in separate terminals.

Account, Transaction, and the BFF are separate origins in every environment, local
and deployed, so the frontend calls each one by its absolute URL instead of relying
on a dev-server proxy. Locally those absolute URLs just happen to share the
`localhost` host with a different port per service:

| Service       | Local URL               |
| ------------- | ----------------------- |
| Account       | `http://localhost:8070` |
| Transaction   | `http://localhost:8071` |
| Responses BFF | `http://localhost:8080` |

## Environment

| Variable                   | Purpose                                                     | Local default                     |
| -------------------------- | ----------------------------------------------------------- | --------------------------------- |
| `VITE_ACCOUNT_API_URL`     | Account API base URL (including `/api`)                     | `http://localhost:8070/api`       |
| `VITE_TRANSACTION_API_URL` | Transaction API base URL (including `/api`)                 | `http://localhost:8071/api`       |
| `VITE_RESPONSES_API_URL`   | Responses BFF chat/stream endpoint                          | `http://localhost:8080/responses` |
| `VITE_RESPONSES_BFF_URL`   | BFF base URL for authentication (`/auth/login`, `/auth/me`) | `http://localhost:8080`           |

Active browser reads call Account and Transaction directly, authenticated with the
same application JWT Identity issues through the BFF at login. Legacy REST client modules remain in
the source tree, but are not used by the in-scope financial screens.

The frontend signs in through the [Responses BFF](../../responses-bff/README.md) at `/auth/login`, keeps only the short-lived application JWT in browser storage, and restores verified identity through `/auth/me`. Profiles require a supported role and positive `identity_version`; only customers carry `customer_id`. Navigation uses the persisted name, with an email fallback. The frontend does not create fixed bearer tokens or synthetic profiles.

## Identity Workspaces

- Customers retain the banking routes, direct Account/Transaction reads and BFF chat.
- Administrators use `/admin/operators` to list operators, activate or deactivate them, and reset their passwords through the BFF's `/admin/operators` endpoints. The protected `/admin/operators/create` page reuses the shared creation form and returns to the list after successful creation or cancellation. Operators/Customers navigation uses primary styling for the active tab and a bordered card background for the inactive tab. Persisted status must be `active` or `inactive`; the required ISO `updated_at` response field is displayed in the administrator's profile locale and browser time zone, with the original timestamp available on hover. Lifecycle fields come from identity responses, not JWT claims. The relocated `app/business-api/identity` service remains behind the BFF; browser endpoints are unchanged. Passwords remain transient and are cleared on submission or dismissal. Operator and customer action confirmations reuse the shared AlertDialog: a portal-backed centered modal with a dark overlay, z-index layering, focus trapping and cancellation autofocus. Errors stay inside the modal; operator creation remains a separate page. Pending operations disable dismissal until the list is refreshed; session unmount aborts pending work.
  Operator creation uses required, trimmed first/last names (50 characters each),
  email up to 120 characters and passwords of 12–256 characters. Labels are localized
  in en/es/pt; invalid payloads are rejected before transport. Existing nullable staff
  names remain readable without inventing names or a customer association.

- Administrators also use `/admin/customers` to list existing customer users and
  confirm activation/deactivation of sign-in access through explicit BFF endpoints.
  The localized list shows customer membership, persisted status and update time,
  including inactive users. Each change revokes prior sessions; activation requires
  a fresh sign-in. Banking customer status and financial data remain unchanged.
  Customer creation, deletion and password reset are unavailable. Loading, empty,
  retry, safe errors, revoked-session logout and pending-operation cancellation follow
  the operator workspace patterns. No browser Identity URL is introduced.
- Operators use `/operator`, which explicitly states that reviewer queues and dispute decisions are unavailable. Neither staff shell mounts financial screens or chat providers.

Direct and nested routes are role-guarded; unknown staff paths return to their workspace. Login destinations cannot redirect to another role's workspace or an external URL. Role guards are UI isolation, not a replacement for server authorization.

Login, logout and cross-tab token changes cancel pending identity work, clear query caches and notifications, and remount the authorized shell to discard local conversation state. Staff and administrator UI uses the profile's en/es/pt locale; logout resets it to English.

Run `npm test`, `npm run lint` and `npm run build` for frontend checks. Administrator client tests resolve request paths against a synthetic base URL so they work both with a configured BFF URL and without local Vite environment files, as in CI. This test base does not change production transport configuration. Identity tests cover contracts, route mount isolation, session reset orchestration and administrator form handlers using the existing Node test environment. These are not browser or live-backend acceptance evidence. Manual checks still include three-role deep links and refresh, lifecycle persistence, expired/revoked sessions, locale display and cross-user logout isolation.

## Localization

The [locale provider](src/context/UiLocaleProvider.tsx) uses the authenticated BFF
profile's exact `es`, `pt`, or `en` locale. Missing, regional or unsupported values fall
back to English; clearing the profile returns the UI to English. Login is always English.
There is no browser-language detection, language selector or separately stored UI locale.

The independent JSON catalogs for [English](src/locales/en.json),
[Spanish](src/locales/es.json) and [Portuguese](src/locales/pt.json) have matching flat
UI keys and nested transaction groups. [TypeScript configuration](src/i18n.ts) imports them statically; JSON separation
does not introduce lazy loading or network requests. The catalogs cover navigation, financial screens, loading,
empty and retry states, chat controls and generic approval controls. Product labels are
translated for display; stored values, identifiers, precision and conversation messages
are not rewritten. The chat welcome is static localized UI and does not send an automatic
request to the agent. Actual agent responses use the separately verified signed backend
locale context, not frontend translation.

The `transactions.types`, `transactions.categories`, and `transactions.statuses`
groups translate six types (including Payment), six categories, and four statuses
in the financial table. Unknown values retain their original label; nulls show the
localized unavailable state. Backend values still drive filters and calculations.
Agent-generated Markdown, merchant names and channels are not translated by these groups.
Nested lookups explicitly enable the dot separator without changing flat-key lookup.

Controlled [BFF error codes](../../responses-bff/README.md#controlled-errors) are mapped
to local UI messages. Raw backend details and unexpected exception messages are not
displayed; login errors remain English.

The latest frontend suite passed with 52 tests; the focused i18n suite passed with
16 tests, covering transaction labels, catalog parity, timeline/recommendation
templates and unknown-label fallback. Edited-file lint and production build passed;
the build retains a large-chunk warning. Full TypeScript checking previously reported existing errors in chat rendering/provider
types and legacy BFF mocks. Authenticated browser localization, responsive layouts and
live multilingual conversations were not validated in this change.

## Account Page

The Account page calls `GET /accounts` on the Account API directly with the application
JWT (not through the BFF). Account scopes the result to savings and checking products
owned by the verified user/customer association. One account is displayed directly;
multiple accounts expose a selector with the type and masked number (product ID
fallback). Loading, retryable errors, and no-account states are explicit.

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
`GET /cards` on the Account API directly, authenticated with the same application JWT.
It displays the verified customer's
credit and debit products, not cards inferred from the selected bank account.
Each card has a separate read-only panel with its stored type, masked number, product
ID, and status, followed by a prominent balance, a separate credit limit, and opening
and expiration dates. Amounts include their currency and thousands separators without
converting decimal strings to floating-point numbers. Card numbers are masked by the
Account API before reaching the browser. Nullable fields display `Not available`; decimal
strings are preserved without estimating debt, available credit, or utilization.

The card grid retains empty column tracks: one card has the same width as each
card in a two-card desktop layout rather than expanding across the entire row.

Loading, no-card, error, retry, and rejected-session messages are explicit. User
changes and retries clear previous rows and abort old requests. A `401` message
asks the user to sign in again but does not itself clear the authentication context.
The page is read-only: payments, recharge, blocking, and limit changes remain
unavailable, with no simulated operations or financial fallback.

## Dashboard and Analytics

Both screens use [FinancialOverview](src/components/FinancialOverview.tsx) with
direct, JWT-authenticated Account and Transaction reads. Account selection uses
`GET /accounts`; transactions use `GET /{product_number}/history` on the Transaction
API directly. The default date window covers today
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
or operations.

## Transaction Disputes

The [support-cases list](src/pages/SupportCases.tsx) and
[case detail/timeline](src/pages/SupportCaseDetail.tsx) pages, at `/support-cases` and
`/support-cases/:caseId`, read and act on Transaction's `/api/support-cases` REST
surface directly through [disputeClient.ts](src/api/disputeClient.ts), authenticated
with the same application JWT as the rest of the direct reads above, never through the
BFF. A [`ReportDisputeDialog`](src/components/ReportDisputeDialog.tsx) is wired into
the Analytics transaction table for `Approved` rows and opens a new case from a
customer-entered reason.

Reporting is hidden for transactions older than the approved 365-day window,
using the real clock, and uses a light-blue outline trigger. It does not yet hide
the trigger for an existing active case; the backend rejects that submission.
Resolved transactions can currently be reported again. Eligibility also accepts
approved deposits; restricting transaction types requires an explicit policy decision.

Case outcomes currently do not create financial movements, update balances, or
block cards. The approval and provisional-credit wording must not be treated as
evidence that those actions occurred. Any future credit should appear as a separate,
case-linked movement on its posting date, not rewrite the original transaction.

Recommendation and timeline message templates are localized in en/es/pt, while the
customer's reason remains unchanged. Generic translated messages omit free-form
manual-resolution notes and reviewer-assignment suffixes; the original audit data
remains persisted. On 2026-10-02, 52 frontend tests (including 16 focused localization
tests), edited-file lint, and the production build passed. The existing bundle-size
warning remains. These checks do not establish authenticated three-language browser parity.

The detail page shows the case status, an approve/decline gate while
`WAITING_USER_APPROVAL`, the full event timeline, and the single post-resolution
recommendation card with an explicit dismiss action once a case resolves favorably. All
status, resolution, and event values are machine-readable codes translated for display
through a dedicated `support-cases.*` i18n namespace in all three locale catalogs.

The backend's `DISPUTE_WINDOW_DAYS` demo policy (365 days, evaluated against the real
system clock) rejects opening a _new_ dispute once every loaded transaction falls
outside that window; this is a dataset-staleness constraint, not a frontend bug.

## Validation

```powershell
npm test
npm run test -- --coverage.enabled=true --coverage.reporter=text-summary --coverage.reporter=json-summary --coverage.reporter=html
npm run lint
npm run build
```

Frontend CI coverage uses Vitest's V8 provider and requires `@vitest/coverage-v8` in `devDependencies`.

Financial arithmetic and pagination tests passed (19 tests), as did the frontend
build and focused financial lint. Global lint still reports unrelated existing
errors in WidgetRenderer, two UI components, and Tailwind configuration.

The card page compiled successfully, and the user confirmed local credit/debit card
display. The Account API's JWT-authenticated contract suite passed, including masking
and ownership cases (see the [business-api guide](../../business-api/README.md)). Card-specific browser recovery and complete two-user parity
have not yet been recorded. The user supplied desktop screenshots of the card panels
and Dashboard. Subsequent card-grid, Account, and Dashboard presentation changes
passed build and focused lint; the 19 frontend tests passed again. The latest layout
has not been independently inspected in an authenticated browser session. Account
retains inherited placeholder-link accessibility diagnostics; global lint is not clean.

Desktop browser balances and transaction rows matched direct, JWT-authenticated Account
and Transaction reads for
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
Hosted identity transport and deployed financial parity are not verified; the
separately tracked real-data verification checklist lives outside this public
repository. Payment submission and attachment upload are not active features.
