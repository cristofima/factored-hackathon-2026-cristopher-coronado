# Identity service

Dedicated credential and principal-lifecycle REST service. The Responses BFF remains
its browser facade; it has no database access. Identity owns Argon2 verification,
HS256 token issuance, persisted profiles, operator and customer-user lifecycle, and identity audit.
It does not own financial data, dispute verdicts, or a real reviewer queue.

## Contracts

- Each principal has exactly one controlled role: `customer`, `operator`, or `admin`.
  Roles use integer primary keys and unique closed-catalog names; `UserRole.role_id`
  stores the association, while JWT/profile `role` remains the canonical name.
  Administrators are Users with the admin role, not a separate Admin table.
- New operator requests require trimmed, nonempty `first_name` and `last_name`,
  each at most 50 characters. Display names are derived from those fields; legacy
  nullable components are not guessed or split and retain the User.name fallback.
  User email is limited to 120 characters and User.name to 101 characters.
  `CustomerUser` maps customer principals to real customers; staff have no invented
  customer association. Operators use the stable `user_id` key; revision
  `20261004_0010` removes the optional simulated reviewer mapping and archives
  existing mappings in `legacy_operator_service_agents`, without live foreign keys.
  Support-case real ownership references `operators.user_id`; catalog snapshots
  never grant operator authority.
- Users have database-constrained `active`/`inactive` status, UTC `created_at` and
  `updated_at`, and positive `identity_version`. New operators start inactive.
- JWTs include `sub`, `email`, `locale`, `role`, `identity_version`, `iss`, `aud`,
  `iat`, and `exp`; only customer JWTs include `customer_id`. Profiles additionally
  expose `name`, `status`, and ISO `updated_at`; these are not JWT claims.
- BFF, Account, and Transaction check current persisted identity state without
  caching. Inactive or stale-version tokens fail with 401; forbidden roles with
  403; unavailable Identity with 503. Existing admitted streams are not cancelled.
  Legacy role-less tokens require a coordinated fresh login.
- Status/password changes increment the identity version and atomically update
  timestamps and audit. Passwords, hashes, and tokens must never enter logs.

| Method     | Route                                       | Access                                                        |
| ---------- | ------------------------------------------- | ------------------------------------------------------------- |
| POST       | `/auth/login`                               | Email/password through BFF                                    |
| GET        | `/auth/me`                                  | Application bearer through BFF                                |
| POST       | `/internal/introspect`                      | `AUTH_INTERNAL_SECRET` bearer; application token in JSON body |
| GET / POST | `/admin/operators`                          | Current admin bearer through BFF                              |
| POST       | `/admin/operators/{user_id}/activate`       | Current admin bearer                                          |
| POST       | `/admin/operators/{user_id}/deactivate`     | Current admin bearer                                          |
| POST       | `/admin/operators/{user_id}/reset-password` | Current admin bearer                                          |
| GET        | `/admin/customers`                          | Current admin bearer through BFF                              |
| POST       | `/admin/customers/{user_id}/activate`       | Current admin bearer through BFF                              |
| POST       | `/admin/customers/{user_id}/deactivate`     | Current admin bearer through BFF                              |

Customer administration lists existing customer-role Users, including inactive
ones, with validated `CustomerUser` membership to a persisted Customer. Staff,
missing targets, and malformed customer memberships cannot be changed. There is no
customer creation, deletion, or password-reset endpoint. Each accepted activation
or deactivation, including a repeated same-status request, increments the version
and atomically records `customer_activate` or `customer_deactivate` audit with its
actor and target. Older sessions stay revoked after reactivation; a fresh login is
required. These operations never change banking Customer status or financial data.
The forward-only `20261003_0008` migration widens the audit action constraint and
must be applied separately through the approved database migration workflow before
using these endpoints; applying it is not part of offline tests.

The introspection secret is distinct from `JWT_SECRET_KEY` and the agent-only
`INTERNAL_IDENTITY_SECRET` HMAC envelope. Staff cannot use customer chat or financial
REST routes. Current operators have a separate direct Transaction review surface:
consented available cases, exclusively assigned cases and owner-only detail.
Identity authenticates and revalidates those operators; Transaction owns claim
policy and audit. See the [Transaction guide](../transaction/README.md).
Assigned-operator verdicts and recorded effects are implemented in Transaction;
reassignment remains out of scope. Implementation does not establish hosted or
financial end-to-end acceptance.

## Configuration and local tooling

Supply environment values explicitly; the service never discovers credential files.

| Variable                      | Purpose                                             |
| ----------------------------- | --------------------------------------------------- |
| `DATABASE_URL`                | Approved PostgreSQL connection                      |
| `JWT_SECRET_KEY`              | HS256 key, at least 32 characters                   |
| `JWT_ISSUER` / `JWT_AUDIENCE` | Shared application JWT issuer/audience              |
| `AUTH_INTERNAL_SECRET`        | Protected introspection key, at least 32 characters |
| `ACCESS_TOKEN_MINUTES`        | 60 by default, range 1–60                           |

Access expiry is absolute from issuance, not an inactivity timeout. Explicit environment
values override the default. Restart Identity after changing the lifetime;
already-issued JWTs retain their original expiry.

From repository root, only after authorizing stack startup:

```powershell
rtk proxy uv sync --directory app\business-api\identity --frozen --group dev
rtk proxy uv run --project "app\business-api\identity" --env-file "app\business-api\identity\.env" uvicorn identity.main:create_app --factory --port 8090
```

The local tasks load each consumer's ignored `.env`: Identity, Account,
Transaction, and Responses BFF. Keep `JWT_SECRET_KEY`, `JWT_ISSUER`,
`JWT_AUDIENCE`, and `AUTH_INTERNAL_SECRET` identical across those four services.
The introspection key must differ from `INTERNAL_IDENTITY_SECRET`; the agent and
normal data ingestion do not need the three issuer/audience/introspection settings.
Identity, Account, and Transaction need `DATABASE_URL`; the BFF must not receive it.
Each service owns `.env` and a credential-free `.env.example`, including the agent.
There is no root dotenv configuration; service tasks load each service's `.env`.

BFF/Account/Transaction retain the compatibility setting `AUTH_USERS_ENDPOINT`
(default `http://127.0.0.1:8090`) for this service despite the Identity rename.
PostgreSQL connection and statement timeouts are bounded to three seconds.

## Explicit administrator bootstrap

Bootstrap is never invoked at application startup. After separately approving the
specific database target and write operation, run the CLI with environment supplied
by the operator:

```powershell
uv run --directory app\business-api\identity banking-bootstrap-admin --email <approved-email> --locale en --confirm-bootstrap
```

The default mode requires `--email`, `--locale`, and `--confirm-bootstrap`; `--name`
is optional. It prompts for a hidden password and matching confirmation, even when
administrator environment credentials are present.

For explicitly opted-in noninteractive provisioning, securely supply
`ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` in the operator's environment,
then run against the separately approved target:

```powershell
rtk proxy node -e 'const p=require("path"),s=require("child_process");const data=p.resolve("app","business-api","data",".env").split(String.fromCharCode(92)).join(String.fromCharCode(92,92));const r=s.spawnSync("uv",["run","--no-sync","--env-file",".env","--env-file",data,"banking-bootstrap-admin","--credentials-from-env","--locale","en","--confirm-bootstrap"],{cwd:p.resolve("app","business-api","identity"),stdio:"inherit"});process.exit(r.status ?? 1);'
```

This local example loads Identity runtime settings and the existing Data bootstrap
credentials without relocating seed passwords. Both files must target the same
approved database; later files and existing process variables can override values.
Run from the repository root in PowerShell after syncing Identity dependencies.
This verified Node wrapper preserves the Windows Data dotenv path through RTK/uv
argument parsing. The bootstrap is one-time provisioning, not a login/reset command.

Environment mode rejects missing/blank credentials and a simultaneous `--email`;
it never falls back to a prompt. Administrator passwords are preserved exactly and
must satisfy the 12–256-character input contract. `DEMO_USER_PASSWORD` remains the
separate customer-seeding credential (outer whitespace is trimmed by that existing
contract). When both are configured, either provisioning path rejects equal
passwords before connecting to the database. Keep both variables configured during
provisioning to enforce that comparison; this is not a password-history comparison.

The CLI refuses an existing administrator or email; it does not reset, promote, or
seed an administrator automatically. First-admin creation is serialized on the admin
role row. Success output identifies no email and contains no credentials. The admin
identity is the operator-supplied bootstrap email, not a default or a seeded customer.
Never put passwords in source, command arguments, or a provisioning manifest.

Provisioning order is explicit: approve target/backups and the legacy activation
policy, apply [data migrations](../data/README.md#migration-prerequisites), run
the existing `run_pipeline.py` only if the approved customer data needs loading,
then separately seed selected customer users and bootstrap the first administrator.
Ingestion never provisions users or an administrator automatically.

## Package responsibilities

- [services](src/identity/services/) contains identity operations, explicit administrator
  bootstrap and customer demo provisioning.
- [models](src/identity/models/) contains API and provisioning DTO schemas; persisted
  tables remain owned by the shared package.
- [main.py](src/identity/main.py) remains the application launch entrypoint.
  [bootstrap.py](src/identity/bootstrap.py) retains the compatible module CLI;
  the console command targets `identity.services.bootstrap:main`.

## Explicit customer demo provisioning

[provisioning.py](src/identity/services/provisioning.py) owns customer identity creation and
refresh, role and association checks, Argon2 hashing, profile normalization and
audits. Each explicit call commits the selected cohort once. Refresh rotates the
credential and identity version; it is not a name-only repair.

The compatible [Data CLI](../data/README.md#explicit-demo-identity-seeding) supplies
environment inputs and writes a credential-free manifest. Normal ingestion and
service startup never invoke provisioning. Database writes and seeding require
separate explicit authorization.

## CI/CD

[Identity CI](../../../.github/workflows/ci-identity.yml) runs Python 3.11 dependency
sync, syntax checks and synthetic tests on matching pushes and pull requests. It
uploads JUnit evidence and rejects stale deployment requirements through the shared
`ci-python` action's optional `deployment-requirements: requirements.txt` input.
[Identity CD](../../../.github/workflows/cd-identity.yaml) repeats validation before
OIDC-authenticated deployment to an existing App Service in `Development`. It only
deploys `main`; OpenAPI exposure and runtime readiness checks are deferred.

The root [azd manifest](../../../azure.yaml) targets Identity through the
explicit `resourceName: ${AZURE_IDENTITY_APP_NAME}`, matching the other services, and copies
`banking_shared` into its deployment package. [Terraform](../../../infra/main.tf)
defines the fifth App Service and exports `AZURE_IDENTITY_APP_NAME`
plus `IDENTITY_URI` from its actual hostname. CI/CD requires the app-name
output as a GitHub Development variable: deployment and preflight target that
exact name, just like the other services. Identity reuses Terraform's existing `database-url` secret with
secret-scoped managed-identity access and coordinated consumer settings; the BFF
has no database setting. This shared PostgreSQL administrator credential is an
approved prototype tradeoff, not least-privilege database isolation. See the
[infrastructure guide](../../../infra/README.md) for authorized rollout and rollback.
Provisioning, approved migrations, network/database grants, secret configuration
and deployed acceptance remain separate gates; neither workflow creates users or
bootstraps administrators.
See [workflow configuration](../../../.github/workflows/README.md#identity-deployment-cd-identityyaml)
for all GitHub variables and App Service settings, including the factory startup command.

Regenerate the Oryx runtime artifact from the dependency manifest for Linux Python 3.11
when dependencies change, using the repository's `uv pip compile` convention:

```powershell
rtk proxy uv pip compile app\business-api\identity\pyproject.toml --no-emit-package banking-shared --python-version 3.11 --python-platform x86_64-unknown-linux-gnu -o app\business-api\identity\requirements.txt
```

The excluded shared distribution is supplied as source by the packaging hooks;
its transitive runtime dependencies remain in the compiled requirements. Successful
CI, metadata preflight or deployment does not establish startup, hosted login or
PostgreSQL acceptance.

## Verification boundaries

```powershell
rtk proxy uv run --directory app\business-api\identity --offline python -m pytest -q --tb=short
```

Synthetic tests cover roles, profiles, token version/revocation, fail-closed
associations, lifecycle audit, explicit bootstrap and
[customer provisioning](tests/test_provisioning.py), including cohort commit and
pre-session validation. Shared-schema migration tests
live in [data tests](../data/tests/test_identity_migrations.py).

Synthetic SQLite success is not PostgreSQL migration/backfill acceptance. Live
migration rehearsal, bootstrap, HTTP/browser checks, least-privilege database grants,
and deployment remain separate approval and evidence gates. No production reviewer
or financial effect is enabled by this service.
