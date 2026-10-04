# Transaction service

Transaction REST reads and customer dispute routes verify the browser application JWT.
MCP tools use the separate short-lived internal agent bearer; it cannot authorize
operator access. Business logic retains customer ownership checks.

## Operator queue and takeover

Every operator request validates the HS256 application JWT and calls Identity's
`POST /internal/introspect` to verify current active status, role and identity version.
The existing `JWT_SECRET_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, `AUTH_USERS_ENDPOINT` and
`AUTH_INTERNAL_SECRET` configuration applies. Only `operator` identities are allowed;
customers, administrators and agent identities cannot use these routes.

| Route                                                              | Result                                                                          |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------- |
| `GET /api/operator/support-cases?view=available&offset=0&limit=50` | Unclaimed, customer-consented `IN_REVIEW` queue (default view)                  |
| `GET /api/operator/support-cases?view=assigned&offset=0&limit=50`  | Cases assigned strictly to the authenticated operator, including resolved cases |
| `GET /api/operator/support-cases/{case_id}`                        | Assigned operator's own case detail only                                        |
| `POST /api/operator/support-cases/{case_id}/claim`                 | Exclusive claim; empty request body; returns owned detail                       |

Both views permit nonnegative offsets and limits from 1 to 100. Omitting `view`
selects `available`; `assigned` filters only by `assigned_operator_sub` matching the
verified principal's `sub`, without status or consent restrictions. Claiming removes
a case from `available` and makes it discoverable in its owner's `assigned` view.
Results are ordered by opening time and case ID, not by an invented risk-priority policy.
The page contains `items`, `total`, `offset`, `limit`. Each item contains `caseId`,
`status`, `openedAt`, `updatedAt`, `triageOutcome`, `claimVersion`; customer IDs,
reasons, product/transaction IDs and financial values are omitted.

Owned detail adds `assignedOperatorSub`, `claimedAt`, `reason`, `transactionId`,
`productId`, `events`. Events contain `eventId`, `eventType`, `actor`, `message`,
`createdAt`, `operatorSub`, `operatorIdentityVersion`, `claimVersion`.
Event messages preserve original audit text, including historical simulated wording;
that wording is not evidence of human investigation, settlement or product protection.
Owned historical detail remains accessible after a status change.

Errors use `detail.code`: `401 AUTH_REQUIRED` (with `WWW-Authenticate: Bearer`),
`403 OPERATOR_REQUIRED`, `503 SERVICE_UNAVAILABLE`, `404 CASE_NOT_FOUND` for missing,
unclaimed or foreign detail, and `409 OPERATOR_CLAIM_CONFLICT` for unavailable claims.
Repeating a successful claim also returns `409`; no reassignment is supported.
Invalid `view` values or pagination parameters return HTTP `422` validation errors.

A conditional SQLAlchemy update performs eligibility checking and ownership assignment
atomically. The claim timestamp/version and `OPERATOR_CLAIMED` event commit together;
audit failure rolls back the claim. Consent requires a customer `APPROVAL_GRANTED`
event. Archived `legacy_assigned_agent_id` neither grants nor blocks operator authority.
New reviews no longer assign synthetic ServiceAgent reviewers. Stored fraud-score
routing is retained; missing scores still escalate without estimating a score.
Taking over does not resolve a case or change balances. There is no operator verdict,
financial action, reassignment, new login or conversational specialist endpoint.

## Schema prerequisite

Apply the data module's Alembic migrations through revision `20261004_0010` before
running this version. Revision 0009 adds claim/time/version/audit fields; revision
0010 binds nullable real ownership to `operators.user_id` with deletion restricted.
Claim requires that persisted Operator as well as current Identity introspection;
missing local persistence returns `503 SERVICE_UNAVAILABLE` without assigning ownership.

Revision 0010 archives the catalog as `legacy_service_agents`, copies former optional
operator mappings to `legacy_operator_service_agents`, removes that live mapping,
and renames historical case assignment to `legacy_assigned_agent_id`. Original audit
text and genuine ownership are preserved; simulated IDs are never converted to real
ownership. Orphan real owners fail migration preflight. Downgrade is deliberately
refused to preserve history.

Customer resolution permissions remain unchanged: the owning customer can still
resolve an `IN_REVIEW` case after takeover. This changes status, not real ownership
or claim audit, and operator-owned detail remains readable. Claim exclusivity covers
competing operators, not exclusive verdict authority; customer resolution and claim
are not jointly serialized.

## Validation

From the repository root:

```powershell
rtk proxy uv run --directory app\business-api\transaction python -m pytest tests -q
rtk proxy uv run --directory app\business-api\data python -m pytest tests\test_operator_claim_migration.py tests\test_identity_migrations.py tests\test_service_agent_retirement.py tests\test_legacy_manifest_verification.py -q
```

`test_operator_postgres.py` is an opt-in PostgreSQL concurrency check. It requires both
`OPERATOR_TEST_ALLOW_WRITES=1` and an externally supplied `OPERATOR_TEST_DATABASE_URL`
pointing at an explicitly authorized disposable test database, never production.
It creates a uniquely named schema with synthetic records and drops that schema on
completion. Two competing sessions must produce exactly one winner, one controlled
conflict and one claim audit, with no resolution. It does not load credential files.

```powershell
rtk proxy uv run --directory app\business-api\transaction python -m pytest tests\test_operator_postgres.py -q
```

Without explicit configuration this test skips. SQLite regressions do not prove
PostgreSQL concurrency or deployed end-to-end identity transport. Those gates remain
open; no disposable-database concurrency execution is recorded here.

Separately authorized local PostgreSQL execution on 2026-10-04 upgraded revision
`20261003_0008` to `20261004_0010`. Backup integrity and read-only preservation checks
passed: original business rows, five cases, 24 events, legacy catalog/mappings and
Operator ownership constraints were retained. One concurrent login added an identity
audit; all 62 original audit records were verified unchanged. Restore rehearsal and
remote rollout were not performed. See the [data guide](../data/README.md#scope).

After assigned-list integration, the focused `tests\test_operator_cases.py` run
passed 13 tests. This is synthetic service coverage, not authenticated browser
acceptance or operator-verdict authority.
