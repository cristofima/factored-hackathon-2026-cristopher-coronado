# PostgreSQL Shared Models and Dummy-Data Replacement Plan

> **Historical evidence; superseded for backlog.** [Issue #24](https://github.com/cristofima/factored-hackathon-2026-cristopher-coronado/issues/24) and its linked deliverables own current acceptance. Unchecked items and open groups were transferred by their ID/DATA/DEPLOY identifiers, not completed. This document retains dated evidence, which does not prove current runtime acceptance.


## Purpose

Define a safe migration path to:

1. Maintain the shared SQLModel package consumed by `data`, `account`, `transaction`, and Identity; the BFF is DB-free.
2. Double-check implemented PostgreSQL reads across every active service against approved persisted records.
3. Show real financial information through direct JWT-authenticated Account/Transaction REST; identity/admin facades and chat cross the BFF.

This plan aligns with the repository constraints: Account/Transaction active workflow, English tool schema/instructions, and service-layer ownership authorization.

## Current status and next gate

Shared schema/database helpers and Account/Transaction persisted reads are implemented.
Dedicated Identity owns authentication/profile persistence; the BFF is DB-free.
Account, Dashboard and the ProductDetail read-only card catalog use direct authenticated
Account/Transaction reads without mock fallback. Payments, investments, beneficiaries
and card mutations remain unavailable; inactive legacy modules remain in the tree.

Phase 5 verifies active reads and frontend parity independently of support-case work.
Older BFF financial-read assertions and checked historical results below describe the
superseded topology, not current Identity migration or browser/deployed acceptance.
Local migrations through `20261004_0010` and authorized identity bootstrap/refresh
are recorded as completed. The 2026-10-04 operator migration preserved original
records and archived simulated reviewer data without backfilling real owners;
see the [data execution evidence](app/business-api/data/README.md#scope).
Local preservation and synthetic verification do not close remote migration,
PostgreSQL claim concurrency, current three-role runtime or parity gates.

### Implementation checklist

Checked items record code and existing coverage, not fresh execution in this session. BFF financial/SQLite/cards and standalone Analytics rows below are historical successes under the previous topology; they do not assert current BFF DB access or current-route acceptance.

- [x] Shared SQLModel package, session helpers, data compatibility imports, and Alembic metadata wiring.
- [x] Account/Transaction customer-scoped queries and ownership integration-test coverage.
- [x] Persisted BFF login, profile, owned-account metadata, and decimal-string/null balances.
- [x] Authenticated BFF account transaction reads with dates, pagination, and record counts.
- [x] BFF financial-read contract/ownership tests using SQLite.
- [x] Frontend persisted customer names and owned-account metadata/selection.
- [x] Real financial consumption on Dashboard and Transaction Analytics without mocks.
- [x] Read-only credit/debit card catalog through BFF, with ownership, masking, null, and decimal-string contract tests.
- [x] Selected two-user PostgreSQL and browser financial parity; local Account chat owned/foreign signed-chain cases confirmed by user evidence.
- [ ] Separate deployed real-data and hosted identity evidence. **Transferred: DEPLOY-06.**

## Scope and Non-Goals

### In scope

- Shared SQLModel definitions for canonical entities currently defined in `app/business-api/data/models.py`.
- Shared database/session bootstrap for PostgreSQL runtime usage.
- `account` and `transaction` service migration from dummy maps to SQLModel queries.
- Authorization checks revalidated against real ownership relationships.
- Regression validation for MCP tool contracts.
- Direct JWT-authenticated Account/Transaction REST reads and real-data presentation for current frontend screens; chat remains through the BFF.
- Explicit unavailable states for capabilities without an approved persisted source.

### Out of scope

- Tool schema redesign in `mcp_tools.py`.
- A second authentication model. Dedicated Identity retains original customer JWT claims and additionally requires `role` and integer `identity_version`; staff tokens omit `customer_id`.
- Durable Functions migration.

## Target Structure

The implemented shared package lives under business APIs:

- `app/business-api/shared/`
- `app/business-api/shared/pyproject.toml`
- `app/business-api/shared/banking_shared/__init__.py`
- `app/business-api/shared/banking_shared/models.py`
- `app/business-api/shared/banking_shared/database.py`

Ownership boundaries:

- `shared`: canonical ORM models and DB plumbing only.
- `data`: ingestion, reconciliation, snapshots, migrations, pipeline orchestration.
- `account` and `transaction`: business logic and authorization decisions, consuming shared models.
- `identity`: persisted credentials/profile/lifecycle, audit and HS256 issuance.
- `responses-bff`: DB-free allowlisted identity/admin facade and customer-only Responses trust boundary; no financial database reads.

## Migration Phases

## Phase 0 - Preconditions and Baseline

> **Consolidated status:** Historical baseline capture is partial; retained MCP baseline and quality/authz confirmation remain DATA-07. Snapshots are conditional, not current UI evidence.

### Goals

- Freeze current behavior and contracts before moving model imports.
- Ensure PostgreSQL data load artifacts and monthly snapshots are available.

### Tasks

- Capture baseline outputs for key account and transaction flows.
- Confirm all current tests pass in each service.
- Record current MCP tool signatures and response shapes.

### Exit criteria

- Baseline tests and sample responses are stored for comparison.

## Phase 1 - Introduce Shared Models Package

> **Consolidated status:** Shared package/import implementation is recorded closed (E1/E3); deployed shared imports and artifact startup remain DEPLOY-03.

### Goals

- Add shared canonical ORM layer without changing behavior.

### Tasks

- Create `app/business-api/shared/banking_shared/models.py` with entities used by runtime paths.
- Move common FK constants and reusable SQLModel definitions from `data/models.py`.
- Add `app/business-api/shared/banking_shared/database.py` with engine and session helpers.
- Keep table names and column definitions identical to avoid migration drift.

### Validation

- Import shared models from a smoke script in all three services.
- Run static checks and tests to confirm no runtime import errors.

### Exit criteria

- Shared models package is importable from `data`, `account`, and `transaction`.

## Phase 2 - Switch Data Service to Shared Models

> **Consolidated status:** Shared metadata/data compatibility implementation is recorded closed; local 0008 is historical completed evidence, while remote revision/readiness remains DEPLOY-04.

### Goals

- Make `data` consume shared models as source of truth.

### Tasks

- Update `app/business-api/data/models.py` to either:
  - re-export shared models, or
  - become a thin compatibility module while imports are migrated.
- Update ingestion scripts and verification modules to import from shared package.
- Validate Alembic `target_metadata` still points to identical schema metadata.

### Validation

- Run data pipeline tests and migration checks.
- Verify no unintended schema diffs are generated.

### Exit criteria

- Data pipeline runs using shared models with no schema changes.

## Phase 3 - Replace Dummy Data in Account Service

> **Consolidated status:** ORM ownership implementation and existing synthetic coverage are recorded closed (E6); current two-user PostgreSQL REST/MCP parity remains DATA-02.

### Goals

- Remove in-memory account ownership/data maps from runtime path.

### Tasks

- Add repository/query layer in `app/business-api/account/services.py` using shared SQLModel models.
- Wire DB session acquisition from shared `database.py`.
- Preserve current tool outputs and service method signatures.
- Keep ownership checks mandatory in service methods before returning data.

### Validation

- Unit tests for successful and denied ownership scenarios.
- Integration test against seeded PostgreSQL records.

### Exit criteria

- Account endpoints/tools are served from PostgreSQL, not dummy maps.

## Phase 4 - Replace Dummy Data in Transaction Service

> **Consolidated status:** ORM paging/ownership implementation and existing coverage are recorded closed (E6); current parity and timezone-independent calendar bounds remain DATA-02/DATA-04.

### Goals

- Remove in-memory transaction data path.

### Tasks

- Add repository/query layer in `app/business-api/transaction/services.py` using shared models.
- Enforce ownership checks for product/account identifiers before returning transaction data.
- Keep MCP contract stable.

### Validation

- Unit + integration tests for authorized/unauthorized transaction access.
- Validate paging/date range behavior against real data.

### Exit criteria

- Transaction endpoints/tools are served from PostgreSQL, not dummy maps.

## Phase 5 - Real-Data Service and Frontend Verification

> **Consolidated status:** Active unresolved acceptance is transferred to DATA-01/02/03/04/05/06/07 and DEPLOY-06. Tasks below are historical scope, not a second backlog.

### Goals

- Prove that each active read uses authorized persisted data and that the frontend displays it accurately.
- Preserve security and turn completion without treating unavailable capabilities as real empty data.

### Tasks

- Inventory REST/MCP reads and UI fields with source, customer scope, environment, and evidence status.
- Compare service outputs with approved PostgreSQL rows using SQLModel, not raw SQL or mock fixtures.
- Verify current Dashboard/Account/ProductDetail financial information through direct JWT-authenticated Account/Transaction REST. Keep chat through BFF → agent → MCP.
- Remove hardcoded financial values and mock fallbacks from in-scope screens. Disable unsupported Payment/investment features rather than add domains.
- Preserve ordinary handoff completion and verify denied access independently of prompt wording.
- Preserve implemented signed-locale runtime context; actual multilingual browser and hosted behavior require separate evidence.
- Record local browser, integration-test, and deployed evidence separately, without secrets or raw customer exports.

### Validation matrix

| Surface                         | Required comparison                                                                                | Required negative/state checks                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Account REST/MCP reads          | Holder, product, balance, currency, and dates match owned persisted records                        | Foreign/missing resources denied; unsupported reads labeled unavailable                       |
| Transaction REST/MCP reads      | Amount, date, merchant, type/channel, ordering, and filters match owned records                    | Foreign product denied; missing/empty results distinguishable from failures                   |
| Identity through BFF facade     | Persisted principal/profile and current role/status/version                               | Invalid/expired JWT denied; no cross-user metadata leakage                                    |
| Responses agent                 | Answers reflect actual Account/Transaction tool results and terminate                              | Invalid signed identity denied; no fabricated values after missing/denied results             |
| Frontend direct financial REST  | Selected account, balances, transactions, currencies, dates, and totals match authorized responses | Switching users/accounts, loading, empty, retry, and expiration do not show stale/mock values |
| Derived snapshots, if displayed | Window and reconstruction/uncertainty policy are visible                                           | Estimates are not presented as authoritative source balances                                  |

Run the matrix for at least two approved seeded users. Inventory all active reads,
including compatibility methods that return empty lists or raise unsupported-operation
errors. Beneficiaries currently raise an unavailable RuntimeError after ownership verification; controlled MCP-boundary unavailability remains DATA-03, not a verified zero-beneficiary count. Current financial summaries/history use Account/Transaction REST, not the DB-free BFF. Verify them against PostgreSQL under DATA-02 before closing frontend parity; snapshot scripts do not imply UI consumption.

### Next-session sequence

1. Refresh current Identity, direct financial REST, MCP and UI inventory (DATA-01).
2. Compare approved two-user PostgreSQL results and ownership behavior.
3. Verify in-scope direct financial REST screens and BFF-only chat (DATA-02, DATA-05, DATA-06).
4. Validate browser states and signed-chain behavior, retaining separate deployed checks.

Define currency grouping, direction/status rules, calendar-date windows, and complete
pagination before analytics totals. Never sum unlike currencies or infer direction from
mock signs. Record counts are not monetary totals. Do not restart completed migrations
or implement new recommendation types or domains unrelated to this real-data slice. The
user explicitly authorized signed-locale context and product-label normalization on
2026-09-30, and separately authorized the transaction-dispute support case to proceed
without waiting for this gate to close (2026-10-01, now CLOSED and its design record
deleted once shipped); that implementation does not close this
real-data gate, and this gate's own checklist below remains independently open.

### Exit criteria

- All active reads are classified and verified or explicitly unavailable, with no dummy-data fallback.
- In-scope frontend financial information matches authenticated responses for both users.
- Ownership, identity propagation, and browser state checks pass; deployed checks remain separately recorded.

### Local verification status

- [x] Inventory active reads and classify financial UI sources.
- [x] Implement signed-locale runtime context and canonical English product ingestion/output; queries use English-only labels while ingestion accepts known Spanish source labels, with automated ownership regressions (2026-09-30).
- [x] Implement static profile-bound UI catalogs, controlled BFF error localization, and display-only transaction type/category/status translations; latest focused i18n suite: 13 passed.
- [ ] Independently verify user-reported historical PostgreSQL label conversion and rerun live parity; authenticated UI localization and multilingual browser conversations remain pending. **Transferred: DATA-02, DATA-05.**
- [x] Compare Account/Transaction and BFF repository results against PostgreSQL for two approved users.
- [x] Verify browser login, owned-account balances and June transaction rows for both users through BFF.
- [x] Implement complete pagination, exact currency-separated movement totals and explicit unsupported UI states.
- [x] Implement read-only card panels and consistent Account/Dashboard presentation; build, focused lint, and 19 frontend tests pass.
- [ ] Complete two-user card browser parity and recovery checks; the 36 BFF account/card tests and user screenshots do not close this matrix. **Transferred: DATA-02, DATA-06.**
- [x] Confirm local Account chat owned/foreign cases through the signed chain (2026-09-30): owned details render; foreign lookup returns `ACCESS_DENIED` and visible assistant denial rather than a blank response.
- [ ] Complete the signed agent-chain matrix in the browser for both approved users. Verified request email replaces the sample profile; missing/empty cases, Transaction chat, multi-turn checkpoint restoration and approval continuation remain unverified end to end. The focused agent suite passed with 23 tests. **Transferred: DATA-05.**
- [ ] Resolve unsupported beneficiary tool semantics and timezone-independent date boundaries. **Transferred: DATA-03, DATA-04.**
- [ ] Complete natural expiration, account-list failure/restoration and normal pointer interaction checks; transaction 503/401 UI tests were simulated. **Transferred: DATA-06.**
- [ ] Verify deployed parity and hosted identity separately. **Transferred: DEPLOY-06.**

This gate is not complete; current acceptance is tracked by
[issue #24](https://github.com/cristofima/factored-hackathon-2026-cristopher-coronado/issues/24)
and its linked deliverables. The transaction-dispute support case, exclusive operator
claim and local migration are implemented separately. Their verification does not
substitute for the unchecked items above or prove final operator adjudication.
Mobile responsive work is outside this session's requested scope.

## File-by-File Change Plan

### Shared package (implemented)

- `app/business-api/shared/banking_shared/models.py`
- `app/business-api/shared/banking_shared/database.py`
- `app/business-api/shared/banking_shared/__init__.py`

### Data service

- `app/business-api/data/models.py` (re-export or compatibility shim)
- `app/business-api/data/database.py` (reuse shared DB helpers where appropriate)
- `app/business-api/data/alembic/*` (metadata import paths only if needed)
- `app/business-api/data/scripts/*` (import path updates)

### Account service

- `app/business-api/account/services.py`
- `app/business-api/account/main.py` (session wiring/config only if required)
- `app/business-api/account/tests/*`

### Transaction service

- `app/business-api/transaction/services.py`
- `app/business-api/transaction/main.py` (session wiring/config only if required)
- `app/business-api/transaction/tests/*`

### Dependency wiring

- `app/business-api/account/pyproject.toml`
- `app/business-api/transaction/pyproject.toml`
- `app/business-api/data/pyproject.toml`
- `app/responses-bff/pyproject.toml`

### BFF and frontend verification

- [BFF identity facade](app/responses-bff/bff/auth.py) and [Identity service](app/business-api/identity/README.md): credential/profile persistence belongs to Identity; the legacy BFF repository is retired.
- [Account REST](app/business-api/account/routers.py) and [Transaction REST](app/business-api/transaction/routers.py): current direct financial surfaces; older BFF PostgreSQL/browser parity does not prove these routes after Identity migration.
- [Account page](app/frontend/banking-web/src/pages/Account.tsx) and [Navigation](app/frontend/banking-web/src/components/Navigation.tsx): persisted metadata/profile checks.
- [Product detail/catalog](app/frontend/banking-web/src/pages/ProductDetail.tsx): authenticated customer-wide catalog, masked numbers, stored balances/limits and nullable dates; no card mutations or inferred bank-account relationship.
- [Dashboard](app/frontend/banking-web/src/pages/Dashboard.tsx): current direct financial REST consumption. Historical standalone Transaction Analytics and BFF comparisons are not current-route runtime acceptance.
- [Legacy BFF client](app/frontend/banking-web/src/api/bffClient.ts): inactive financial compatibility code, not the current browser path. Preserve direct Account/Transaction JWT reads and BFF-only chat.

Ensure each service can import the shared package in local development and deployment packaging.

## Contract and Compatibility Rules

- Do not change MCP tool names, descriptions, or parameter signatures.
- Do not change externally visible response fields unless explicitly versioned.
- Preserve original customer claims (`sub`, `customer_id`, `email`, `locale`, `iss`, `aud`, `exp`) plus mandatory `role` and integer `identity_version`; staff omit `customer_id`. Preserve per-request Identity introspection.
- Keep authorization decisions in `services.py` (not prompts, not frontend filtering).

## Risks and Mitigations

- Import cycles between shared and service modules.
  - Mitigation: shared package must not import from service packages.
- Alembic metadata drift after model moves.
  - Mitigation: validate generated diffs before applying any migration.
- Packaging/import issues in App Service runtime.
  - Mitigation: regenerate requirements and run local startup smoke tests per service.
- Hidden behavior drift from query semantics vs dummy maps.
  - Mitigation: baseline response comparison and explicit regression tests.

## Rollback Plan

- Keep compatibility shim in `data/models.py` until all imports are migrated.
- Migrate one runtime service at a time (`account` first, then `transaction`).
- Restore only compatible artifacts/configuration with the forward schema and current JWT/introspection contract. Never restore dummy financial data, BFF DB access or role-less tokens; database restore/downgrade requires separate approval.

## Suggested Implementation Slices

1. Shared package + data service import migration only.
2. Account PostgreSQL migration + tests.
3. Transaction PostgreSQL migration + tests.
4. Next: inventory and double-check all active persisted service reads.
5. Verify current direct financial REST and BFF-only chat for both users (DATA-02, DATA-05, DATA-06).
6. Capture separate deployed evidence before closing the real-data gate.

Each slice should be independently testable and reversible.

## Definition of Done

- [x] Shared SQLModel package is the single runtime schema source.
- [x] `account` and `transaction` no longer use dummy in-memory ownership/data maps.
- [x] Ownership authorization uses persisted relationships; integration-test coverage exists.
- [ ] Confirm MCP contract compatibility against the retained baseline. **Transferred: DATA-07.**
- [ ] Full local browser path validation passes with approved test credentials and real data. **Transferred: DATA-02, DATA-05, DATA-06.**
- [ ] Every active REST/MCP read is verified against persisted records or explicitly classified as unavailable. **Transferred: DATA-02.**
- [x] In-scope frontend screens show real account/transaction information without mock financial fallbacks.
- [ ] Derived estimates, empty results, unavailable capabilities, and errors are distinguishable. **Transferred: DATA-03, DATA-04, DATA-06.**
- [ ] Deployed real-data parity and hosted identity transport have separate evidence. **Transferred: DEPLOY-06.**
- [ ] Phase 1 can be marked complete and Phase 2 revalidation on real data can be closed. **Transferred: DATA-02, DATA-05, DATA-06, DATA-07, DEPLOY-06.**
