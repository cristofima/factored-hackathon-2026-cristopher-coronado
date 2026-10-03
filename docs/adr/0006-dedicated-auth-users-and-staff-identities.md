# ADR 0006: Dedicated Identity and Independent Staff Identities

| Status   | Date       | Proposed by | Approved by | Supersedes                                                                                                                                                                |
| -------- | ---------- | ----------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Accepted | 2026-10-03 | cristofima  | cristofima  | [0005-frontend-calls-account-and-transaction-directly](0005-frontend-calls-account-and-transaction-directly.md) (identity ownership only; direct financial REST retained) |

---

## Context

Customer-only users and BFF-owned password verification cannot represent staff
without inventing customer records. Administrator provisioning and revocation need
persisted, service-enforced boundaries before real dispute reviewers are enabled.
This decision supersedes the identity-ownership portion of ADR 0005, retaining its
direct browser-to-Account/Transaction financial REST topology and custom JWT choice.

## Decision

Identity owns Argon2 credentials, profiles, role membership, lifecycle, token
issuance and identity audit. The BFF is database-free and exposes allowlisted
login/profile/admin facades, not an arbitrary proxy. Customer chat still crosses
BFF, Responses agent and MCP. Staff cannot use customer financial REST or chat.

Users have stable subjects, unique normalized emails, UTC created/updated timestamps,
active/inactive status and identity version. CustomerUser preserves verified real
customer associations. UserRole permits one controlled customer/operator/admin role.
Role has an integer primary key and a unique canonical name; UserRole references
role_id while JWT/API contracts expose names, never internal IDs. Operator has
structured first_name/last_name (50 characters each); new profiles require both,
while legacy nullable names retain the existing display-name fallback without guessing.
User/Customer email is bounded at 120 characters, Customer names at 50 each and
country at 100. Customer commercial status is independently constrained to Active,
Inactive, Suspended or Closed (legacy null supported); it does not alter login policy.
Operator is a separate staff profile; any ServiceAgent association must be explicit.
An administrator remains User plus admin role, without a separate Admin table.
No user is derived from customer CSVs, and no customer is fabricated for staff.

Customer JWT claims retain sub/customer_id/email/locale/iss/aud/exp and add role and
identity_version. Staff JWTs omit customer_id. BFF and direct financial REST verify
current active identity/version on every request through protected Auth introspection,
without caching, with bounded timeout and fail-closed outages. Application JWT,
Auth introspection secret and agent-only MCP bearer are distinct contracts.
HS256 remains for compatibility; verifier-secret holders can mint tokens, so key
isolation/asymmetric signing is a separate future decision, not a claimed guarantee.

An explicit admin seed service accepts externally supplied credentials; it never
runs automatically at startup or silently promotes an existing customer/operator.
Administrators create operators through fixed-role operations. Identity changes,
version increments, updated_at and secret-free audit commit atomically.

## Rollout and Rollback

Implementation is authorized; live rollout is not verified.

Synthetic migration tests precede target-specific authorized database writes.
Validate mappings and unique associations before removing the mandatory User
customer foreign key. Deploy Auth before callers, migrate identities and coordinate
caller rollout: legacy role-less/version-less tokens require fresh login, not an
implicit privileged compatibility path. Configure AUTH_USERS_ENDPOINT and a separate
AUTH_INTERNAL_SECRET. Remove BFF DATABASE_URL and database grants during rollout.
The existing Terraform stack does not yet provision the additional Auth service.

Downgrade must refuse unrepresentable staff or retained audit history rather than
remove users, fabricate customers or silently discard evidence. Backups, PostgreSQL
migration rehearsal, least-privilege database roles, runtime/browser isolation,
monitoring and deployed rollback require separate validation before production.

## Consequences

Protected REST availability now depends on Identity. Identity revocation takes effect
on subsequent HTTP requests; it does not retroactively cancel an already admitted
stream or replace customer resource-ownership checks. More deployment/configuration
work is required. Identity tests do not establish real reviewer permissions,
dispute adjudication or financial settlement. No reviewer queue/verdict is enabled
by this extraction.
