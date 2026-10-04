# Demo Scope Checklist (Through 2026-10-05)

Condensed execution checklist for the locked MVP scope.

## Objective

Deliver a functional, submittable demo for retail banking customers where users can review financial context, open a support case from conversation, complete an approval-gated workflow with persisted status tracking, and receive one contextual recommendation after resolution. The named scenario is **transaction disputes** (see [the scope ADR](docs/adr/0001-single-workflow-scope-with-dispute-support-case.md)). Case tracking is implemented; financial credits and card blocking are not.

Dataset note: 2026 profiling shows higher monthly transaction counts than 2025 for selected customers. Even so, MVP value is framed around support-workflow clarity and traceability, not high-volume optimization.

## Evidence assumptions

- Positioning claims are constrained to observed dataset behavior for selected customers.
- 2026 has stronger monthly activity than 2025, but the MVP remains focused on workflow
  clarity, approval control, and traceability instead of high-volume optimization.
- Recommendation behavior is limited to one contextual post-resolution suggestion per
  case, with rationale and explicit user opt-out.

## Scope Boundary

In scope:

- Account and Transaction support workflow.
- Case workflow launched from conversation context.
- Persisted case lifecycle and status visibility.
- User approval as a real workflow gate.
- One contextual product recommendation after case resolution, with rationale and opt-out.

Out of scope before deadline:

- Durable Functions migration.
- Full enterprise ticketing platform features.
- Voice-to-text accessibility features.
- Product-domain expansion beyond Account/Transaction.

## Current Snapshot

### Session implementation and local evidence (2026-10-04)

- [x] Customer-only chat/session isolation and read-only dispute consultation safeguards implemented with offline regressions.
- [x] Active Identity operators can exclusively claim consented unclaimed `IN_REVIEW` cases; available/assigned pagination and owner-only detail are implemented.
- [x] SupportCase ownership references Operator subjects directly; simulated ServiceAgent data and mappings are archived without owner backfill (ADRs [0007](docs/adr/0007-real-operator-exclusive-dispute-takeover.md) and [0008](docs/adr/0008-operator-ownership-without-service-agent-catalog.md)).
- [x] Authorized local PostgreSQL upgrade to `20261004_0010` and read-only preservation verification completed. Backup readability/integrity passed; restore rehearsal was not run.
- [x] `/operator/support-cases` supports assigned-case rediscovery, shared operator-perspective timeline, en/es/pt keys, reason/metadata hierarchy and reusable date presets.
- [x] Final focused frontend run: 36 passed; lint zero errors/14 existing warnings; production build passed with existing chunk-size warning. Exact commands are in the [frontend guide](app/frontend/banking-web/README.md#session-validation-2026-10-04).
- [x] Local Transaction connectivity restored by starting its existing task; allowed-origin preflights and controlled 401 retained CORS. No origin/configuration change was required; the user confirmed recovery.
- [ ] Authenticated browser matrix: customer/operator deep links, refresh, pagination, locale display, timeline attribution and cross-user/role isolation.
- [ ] PostgreSQL competing-claim acceptance, deployed migration/parity and backup restore rehearsal.
- [ ] Assigned-operator verdict authority, versioned evidence and final adjudication acceptance.
- [ ] Financial posting/blocking policy and effects, paired real-model quality and hosted identity acceptance.

Implementation/tests and local migration do not close these runtime or business gates.

### Historical Evidence (2026-10-02)

The automatic-resolution observation below predates the explicit-review change and
is superseded for current behavior. Approvals now remain `IN_REVIEW`, confirmed by
the user and historical regression tests. Existing-case UI recovery and product
navigation are implemented; operator adjudication and runtime acceptance remain open.

- A user-created local case was queried read-only in PostgreSQL: persisted risk
  score 2.03, customer approval followed by `fast_track` and
  `fast_tracked_provisional_credit`, with no reviewer assigned. This verifies one
  case's state and events, not a credit posting, card block, full polling behavior,
  chat entry point, or two-user authorization matrix.
- The transaction-age window is 365 days against the real clock; 26 service tests
  pass, including 364-day acceptance and 366-day rejection. Frontend eligibility
  hides older transactions. A screenshot of 2025-10-08 on 2026-10-02 is within that window.
- Localized recommendation/timeline templates in en/es/pt and a light-blue report
  trigger are implemented. Latest frontend suite: 52 passed; focused i18n: 16
  passed; edited-file lint and build passed. Three-language browser parity is open.
- Source inspection confirms no financial posting, balance update, or card-block
  mutation. Existing active cases are rejected by the service but not reflected in
  row eligibility; concurrent creation and repeat claims after resolution remain gaps.

Historical snapshots below describe earlier checks, not closure of these gaps.

Done:

- Single active Account/Transaction workflow and trimmed architecture path.
- PostgreSQL-backed Account/Transaction reads and shared SQLModel package implemented.
- Persisted Argon2 login, JWT propagation, and service-layer ownership checks implemented.
- Verified request profile replaces the sample email. Local browser Account chat returns owned details and a visible foreign-account denial; request-isolation regressions pass.
- BFF-backed customer-name display and owned-account selection implemented.
- Direct Account balances and customer-scoped paginated Transaction APIs consumed by Dashboard and Analytics with BFF-issued JWTs; selected local two-user financial parity passed.
- Read-only credit/debit card catalog through Account, with server-masked numbers and historical contract coverage; user-confirmed local display.
- Account and Dashboard presentation refined; single-card width matches the two-card layout. Build, focused lint, and 19 frontend tests pass, but latest authenticated visual inspection remains pending.
- Data-side monthly snapshot materialization and verification for scoped customers.
- Plan-level scope lock for workflow MVP and closeout expectations.
- Signed-locale runtime context for triage/Account/Transaction (`es`, `pt`, `en`, safe `en` fallback), with automated concurrency coverage; real multilingual conversations remain unverified.
- Shared English product-type catalog and ingestion normalization; queries use canonical English labels. Historical PostgreSQL conversion is user-reported, not independently verified in this follow-up.
- Profile-bound static JSON UI catalogs, localized controlled BFF errors, and display-only transaction types/categories/statuses implemented; latest focused i18n suite: 16 passed. Browser localization remains unverified.
- Transaction-dispute case tracking implemented: persisted cases/events, ownership checks, REST/MCP entry points converging on `SupportCaseService`, deterministic review routing, exclusive Operator claims, approval UI, and recommendation opt-out. Simulated reviewer metadata is archived only. The 365-day window is user-approved; the earlier 26-test result and local case progression are historical evidence, not current adjudication or financial-action acceptance.

In progress:

- Double check of real-data reads across all active services and the authenticated browser path.
- Signed agent-chain verification and remaining browser-state checks after frontend BFF integration.
- Final deployment and closeout evidence alignment.

Dashboard, Transaction Analytics, and the read-only credit/debit card catalog consume
direct Account/Transaction data authenticated with BFF-issued JWTs. Investments, Payments and card mutations show unavailable states; inactive legacy/mock modules
remain in the source tree. Local two-user balance/transaction parity passed, but the
agent now receives verified signed profile context, while beneficiaries has no persisted source.
The gate remains open. Hosted deployment and hosted identity/data-path verification are
separate checks; this checklist does not establish completed hosted validation.

Not done yet:

- Observed browser verification of automatic status polling. Serial 10-second polling
  and manual refresh are implemented; cleanup and pending-sibling reads are tested,
  but persisted browser behavior remains unverified.
- A true held-out conversational evaluation of the dispute workflow (`test_dispute_service.py`'s 22 tests are deterministic service-level regression coverage, not a held-out LLM-quality run); recommendation precision and sampled-case metrics with stated sample sizes.
- Full held-out evaluation run including workflow progression metrics for the broader Account/Transaction workflow.
- Demo slides, video capture, and final submission package.

## MVP Must-Ship Checklist

### 0) Real-data verification gate (next)

The support-case tracking layer was implemented independently; this gate remains open. See the
[service and frontend validation matrix](POSTGRES_SHARED_MODELS_MIGRATION_PLAN.md#phase-5---real-data-service-and-frontend-verification).

Mobile responsive work is deferred. Checked items do not
close the signed-chain, natural-expiration, beneficiary or hosted gates.

- [x] Inventory active REST/MCP reads and visible financial fields by persisted, derived/estimated, unavailable, or mock source.
- [x] Implement and unit-test signed locale context and canonical product-type ingestion/output without changing ownership or MCP signatures.
- [x] Implement static UI catalogs, safe localized BFF error messages, and grouped transaction label translations without changing backend values or ownership contracts.
- [ ] Verify stored-locale responses and authenticated UI localization through real browser conversations; independently verify user-reported historical PostgreSQL label conversion and record hosted evidence separately.
- [x] Compare Account and Transaction outputs with approved PostgreSQL records for two seeded users.
- [x] Verify existing BFF login, profile, balances, and paginated transaction responses against persisted records.
- [ ] Revalidate owned, foreign, missing, and empty-result scenarios through the signed identity chain.
- [x] Validate local owned-account chat through BFF to agent to Account MCP; user screenshot shows account details, full bank number and masked card output (2026-09-30).
- [x] Validate local foreign-account chat: `getAccountDetails(product_number=...)` returns `ACCESS_DENIED`, followed by visible assistant text and `response.completed`, without foreign financial data (2026-09-30).
- [x] Cover workflow request isolation and ownership-denial completion with agent regressions; focused suite: 23 passed.
- [ ] Verify same-conversation multi-turn checkpoint restoration and approval continuation end to end.
- [x] Show real account balances and transactions through direct Account/Transaction REST reads authenticated with the BFF-issued JWT.
- [x] Remove in-scope mock financial values and legacy clients; show unavailable states for unsupported features.
- [ ] Verify account switching, currencies, dates, totals, loading, empty, retry, and expired-session states.
- [x] Define analytics direction/status rules, currency grouping, date windows, and complete pagination before calculated totals.
- [ ] Label derived monthly snapshots as estimates if displayed; do not imply they are source balances.
- [ ] Capture browser evidence for both users without tokens, passwords, or raw customer exports.
- [ ] Complete card-specific two-user browser parity and failure/recovery checks; user screenshots establish display, not the full matrix.
- [ ] Record deployed real-data and hosted identity checks separately from local evidence.

### A) Agent workflow foundation

- [x] Create persisted support-case schema (`support_cases`, `support_case_events`).
- [x] Implement valid state transitions:
  - [x] `OPEN -> WAITING_USER_APPROVAL`
  - [x] `WAITING_USER_APPROVAL -> IN_REVIEW`
  - [x] `IN_REVIEW -> RESOLVED`
- [x] Enforce ownership/authorization on case read/update operations.
- [x] Store event timeline entries for each transition and approval action.

### B) Conversation to case integration

- [x] Add case creation path from conversation context (`reportTransactionDispute` MCP tool).
- [x] Capture case reason, linked account/transaction context, and initiating user.
- [x] Return case ID and initial status back to user-facing flow.

### C) Frontend workflow UI

- [x] Add "Support Cases" (Transaction Disputes) list page.
- [x] Add case detail page with timeline and current status.
- [x] Add user approval UI for at least one meaningful gated action.
- [ ] Verify periodic status refresh in the browser. Polling and manual refresh are
      implemented, with abort cleanup and no retry until both detail reads settle.
      Browser action coordination, identity changes, and persisted parity remain open.

### D) Evaluation and reliability checks

- [ ] Persist case-linked credit movements and update balances atomically under an approved policy.
- [ ] Persist card blocking only for a verified linked card; define release/replacement and no-card behavior.
- [ ] Prevent concurrent duplicate cases and duplicate credits with database-backed invariants.
- [x] Show an existing active case and recover sequential duplicate intake through controlled HTTP 409 handling; historical frontend/transaction tests cover the implemented contract.
- [ ] Define post-resolution reclaim policy and database-level concurrent duplicate protection; sequential recovery does not close these requirements.
- [ ] Define provisional-credit versus final-verdict semantics and eligible transaction types.
- [ ] Verify movements, balances, card state, and case events through both entry points in an authorized runtime run.
- [x] Add truthful financial/card-effect metadata, preserve original audit text through display projections and replace frontend implementation disclaimers with neutral localized review wording.
- [ ] Validate REST/MCP/chat/UI claims end to end in all locales; never present credits or blocks without matching persisted effects.

The checked reliability/approval items below record the earlier synthetic policy,
including its automatic closure path. Current consent routes to real review; these
historical results do not prove an operator verdict or financial effect.

- [x] Add deterministic workflow progression test coverage (conversation-shaped
      case -> approval -> resolved, via `test_dispute_service.py`); a true held-out
      conversational/LLM-quality evaluation of the same flow remains pending.
- [x] Measure workflow reliability (completion without manual DB edits) via the same
      deterministic test suite.
- [x] Measure approval correctness (approval requested only when policy requires it)
      via the same deterministic test suite.
- [ ] Measure recommendation precision for the selected audience (recommended offer relevance on sampled cases).
- [ ] Record sample sizes and offline/simulated labels for every metric.

### E) Demo and closeout package

- [ ] Update submission README with workflow MVP scope and limitations.
- [ ] Prepare slides with workflow states, approval gate, and status tracking evidence.
- [ ] Record demo video including:
  - [ ] Case opened from conversation context.
  - [ ] User approval step.
  - [ ] Status progression through required states.
  - [ ] One contextual recommendation shown after `RESOLVED` with rationale and user opt-out.
  - [ ] Unauthorized access rejection.
- [ ] Verify final deployed URL behavior for both seeded demo users and both languages.

## Daily Execution (Recommended)

- Transaction-dispute support-case schema/APIs/conversation-integration/case pages are
  done (2026-10-01), ahead of the real-data gate per the user's explicit reordering.
- Next: real-data service double check and frontend parity gate; keep failed checks open.
- Then: browser verification of status polling, the held-out workflow evaluation,
  and end-to-end hardening.
- Before submission: evaluation run + slide/video capture; adjust remaining work to actual gate completion.
- Oct 5: final submission buffer.

## Demo Acceptance Criteria

The demo is considered functional when all of the following are true:

- A user can view account/transaction context and open a support case from conversation.
- Displayed financial values match authorized persisted records or clearly labeled derived estimates, without mock fallbacks.
- The case is persisted and visible in a list/detail UI.
- The workflow includes a meaningful user approval gate.
- Case status progression is visible and reaches `RESOLVED`.
- Any claimed credit or card block has a matching persisted action and visible effect; a status or event label alone is insufficient.
- A single contextual recommendation can be shown after resolution and declined by the user.
- Unauthorized cross-customer access is denied and demonstrable.
