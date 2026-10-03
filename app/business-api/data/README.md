# Data Module

This module profiles the LATAM banking CSV dataset, approves a bounded transaction
window, loads it into PostgreSQL, and verifies the resulting rows and source checksums.
Run every command from the repository root.

## Scope

The loader upserts tables in dependency order:

1. `branches`
2. `customers`
3. `service_agents`
4. `products`
5. `transactions`

The pipeline does not populate the `users` table. Create selected demo identities
separately with `seed_demo_users.py` after their customer rows have been loaded.

## Customer and identity schema

Customer email is limited to 120 characters, first/last names to 50 each, and
country to 100. Ingestion trims and case-normalizes customer status to `Active`,
`Inactive`, `Suspended`, or `Closed`; blank/absent legacy values remain null.
Unknown statuses and overlength fields reject loading rather than truncate data.
Customer business status does not change the independent User login policy.

Revisions `20261003_0006` and `20261003_0007` incorporate the final
schema directly; there is no intermediate string-role schema or revision 0008.
0006 preflights legacy identities, bounded fields, and canonical Customer statuses
before any DDL, then creates integer role keys/memberships, bounded User/Customer
fields, and nullable Operator components without invented backfill. Populated
legacy users require explicit `-x legacy-user-status=active|inactive`; credentials,
subjects, locales, and creation timestamps are preserved.
0007 validates the final role catalog and exact customer associations before any
DDL, records migration audits, and removes the legacy User customer foreign key.
Both revisions use frozen/reflected schemas, not mutable application models.
Downgrades reject loss of staff, lifecycle state, or audit history; an empty schema
can downgrade safely. Retain a verified backup for populated rollback and obtain
separate approval for PostgreSQL rehearsal; offline SQLite tests are not live acceptance.

After the specific target, backup, write operation, and legacy activation policy have
been approved, supply their environment explicitly. From repository root:

```powershell
rtk proxy uv run --project app\business-api\data --env-file <approved-env-file> alembic -c app\business-api\data\alembic.ini -x legacy-user-status=<approved-active-or-inactive> upgrade head
```

Replace the policy placeholder with exactly `active` or `inactive`; do not silently
activate legacy users. This generic command is not evidence for any other target.

On 2026-10-03, the authorized loopback PostgreSQL 13.0 database was backed up with
`pg_dump --format=custom` and its archive checked with `pg_restore --list`. Alembic
applied both revisions from `20261001_0005` to `20261003_0007`, with explicit
`legacy-user-status=inactive`: the 10 legacy users had no established lifecycle
column, so the authorized fail-closed policy avoided silently activating accounts.
All nine existing tables retained their counts and content digests; the comparison
reconstructed the removed customer column from CustomerUser. Subjects, credentials,
locales, creation timestamps and customer mappings were preserved. Live reflection
matched runtime CHECK names, bounded/nullability fields, PK/UNIQUE/FK contracts and
indexes, including all 13 additional indexes. All 10 customer memberships and
migration audits were verified; admin and operator counts were both zero.
Activation, staff provisioning, interrupted recovery, concurrency, query-planner
behavior, service/browser acceptance and remote migration remain separate gates.
Do not reset/downgrade a populated database to resolve preflight conflicts: correct
approved source records or mappings, then retry with preserved identity history.

Use the existing `scripts/run_pipeline.py` orchestrator for any separately approved
data load (EDA → scope → load → verification), followed by explicit customer seeding
and explicit [administrator bootstrap](../identity/README.md#explicit-administrator-bootstrap).
Neither ingestion nor service startup automatically migrates or provisions identities.

## Identity/Customer index coverage

CHECK constraints do not create indexes. Revision 0006 creates the additional
User, Customer, Operator and membership indexes; 0007 creates audit indexes.
Runtime SQLModel metadata declares the same names and column order. Safe downgrade
removes only the added indexes and preserves legacy email indexes.

| Index or existing key                                                                                       | Fields                     | Evidence / purpose                                                                                                               |
| ----------------------------------------------------------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Existing `ix_users_email` (unique)                                                                          | email                      | Identity login, email conflict checks, operator-list email ordering; covers both email CHECKs                                    |
| Existing User PK                                                                                            | id                         | Token authentication and lifecycle point lookups                                                                                 |
| Existing Role name UNIQUE / id PK                                                                           | name / id                  | Role resolution and catalog CHECK coverage                                                                                       |
| `ix_user_roles_role_user`                                                                                   | role_id, user_id           | `bootstrap.py` role filter; `service.py` operator-list role join followed by user lookup; email ordering remains a separate sort |
| Existing CustomerUser PK / customer_id UNIQUE                                                               | user_id / customer_id      | Profile lookup and unique customer association                                                                                   |
| Existing Operator PK / service_agent_id UNIQUE                                                              | user_id / service_agent_id | Profile lookup and optional reviewer association                                                                                 |
| Existing Customer PK / `ix_customers_email`                                                                 | customer_id / email        | Account customer/email lookups, seeding and verification cohort filters                                                          |
| `ix_users_status`, `ix_users_identity_version`, `ix_users_locale`, `ix_users_name`                          | Corresponding single field | Explicit CHECK-field coverage only; current authentication reads by PK/email then checks state in Python                         |
| `ix_operators_first_name`, `ix_operators_last_name`                                                         | Corresponding single field | Explicit length-CHECK coverage only; no name search currently                                                                    |
| `ix_customers_first_name`, `ix_customers_last_name`, `ix_customers_country`, `ix_customers_customer_status` | Corresponding single field | Explicit CHECK-field coverage only; current service queries do not filter these fields                                           |
| Existing `ix_identity_audits_target_id`                                                                     | target_id                  | Target audit selection in Identity regression checks; no production audit-list endpoint                                          |
| `ix_identity_audits_action`, `ix_identity_audits_result`                                                    | Corresponding single field | Action selection in boundary tests; both catalog CHECKs covered, result coverage-only                                            |

Each CHECK field has a usable leading index/key column; no duplicate PK, UNIQUE,
or existing composite-prefix index is added. The role/user composite does not
replace the user_id PK: its reverse leading column supports role-to-user traversal.
Low-cardinality status, locale, version and audit catalog indexes may be ignored
by PostgreSQL and incur storage/write overhead; their inclusion satisfies the
explicit CHECK-coverage requirement, not a measured performance improvement.
Name length indexes cover the field, not the `length(...)` validation expression.

No scoped production query filters or sorts User creation/update timestamps,
Customer registration dates, or audit occurrence time. Date and actor indexes
are therefore deferred rather than inventing chronological/admin query patterns.
Existing Product/Transaction date composites remain unchanged and outside scope.
Offline metadata, historical replay, safe downgrade and rejected-transaction
rollback tests verify index contracts; PostgreSQL EXPLAIN/selectivity, transactional
mid-DDL recovery and migration on other targets remain unverified and require separate
authorization. No login, profile, JWT, ownership or lifecycle policy changes accompany indexes.

Offline validation after the index refactor (repository root):

| Exact command                                                                                        | Result               |
| ---------------------------------------------------------------------------------------------------- | -------------------- |
| `rtk proxy uv run --directory app\business-api\data --offline pytest -q --tb=short`                  | 88 passed            |
| `rtk proxy uv run --directory app\business-api\identity --offline pytest -q --tb=short`              | 62 passed            |
| `rtk proxy uv run --directory app\business-api\account --offline python -m pytest -q --tb=short`     | 75 passed, 1 skipped |
| `rtk proxy uv run --directory app\business-api\transaction --offline python -m pytest -q --tb=short` | 86 passed, 1 skipped |

Identity, Account and Transaction emit an existing Starlette/httpx deprecation
warning. Skipped tests are not runtime-verification evidence.

## Product Types

Ingestion normalizes `products.product_type` using the shared
[product catalog](../shared/banking_shared/product_types.py). Canonical labels are
Savings Account, Checking Account, Investment, Mortgage Loan, Personal Loan,
Insurance, Credit Card and Debit Card. Known Spanish source labels, including
both personal-loan spellings, are accepted with surrounding whitespace, case and
accent normalization. Unknown scoped types reject the dimension transaction before
commit; products outside a selected customer filter do not affect that load.

Account, Transaction and BFF category queries use only canonical English labels.
Spanish compatibility belongs to ingestion normalization, not database query filters.
BFF product types and Account
card names are canonical English; Account card `type` remains `credit`/`debit`.
This does not migrate existing database rows. The user reports manually converting
historical labels; that conversion was not independently verified in this follow-up.
Rerun live scoped parity verification before closing the data gate.
The existing manifest count/orphan checks do not independently verify label semantics.

## Pipeline

Use `run_pipeline.py` for normal operation. It executes the individual scripts in this
order and stops if a command fails or EDA does not approve the requested window.

```mermaid
flowchart LR
	A[EDA profile] --> B[Scope selection]
	B --> C[Scoped load]
	C --> D[Load verification]
```

The user supplies `--start-date` and `--end-date`. For a one-day migration, use the same
date for both arguments. The optional `--customer-ids` argument accepts one comma-separated
string and limits customer-owned data to those IDs.

## Environment

The local `app/business-api/data/.env` file must define:

```dotenv
DATABASE_URL=postgresql+psycopg://...
DATA_SOURCE_DIR=C:/Factored/data
DATA_ARTIFACTS_DIR=C:/Factored/factored-hackathon-2026-cristopher-coronado/app/business-api/data/artifacts
DATA_MANIFEST_DIR=C:/Factored/factored-hackathon-2026-cristopher-coronado/app/business-api/data/artifacts
DEMO_USER_PASSWORD=
```

| Variable             | Purpose                                                                           |
| -------------------- | --------------------------------------------------------------------------------- |
| `DATABASE_URL`       | PostgreSQL SQLAlchemy connection URL.                                             |
| `DATA_SOURCE_DIR`    | Directory containing dimension CSVs and the partitioned `transactions` directory. |
| `DATA_ARTIFACTS_DIR` | Directory for EDA profiles and scope manifests.                                   |
| `DATA_MANIFEST_DIR`  | Directory for load manifests. This is a directory, not a JSON filename.           |
| `DEMO_USER_PASSWORD` | Shared password hashed for users created by `seed_demo_users.py`.                 |

The orchestrator derives a new manifest filename from the requested window. A fixed
`DATA_MANIFEST_PATH` is intentionally not used because it would overwrite the evidence
from a previous run.

Always pass the environment file explicitly to `uv`; it is ignored by Git and is not
loaded automatically.

Copy `app/business-api/data/.env.example` to the ignored
`app/business-api/data/.env`, replace its example values, and keep the real password out
of source control.

## Recommended Command

### Migrate one day

This command runs all four pipeline stages for March 1, 2026:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/run_pipeline.py --start-date 2026-03-01 --end-date 2026-03-01
```

### Migrate a date range

This command runs all four stages for every daily partition from March 1 through May 31:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/run_pipeline.py --start-date 2026-03-01 --end-date 2026-05-31
```

`--batch-size` is optional and defaults to `50`.

### Migrate selected customers

For a demo-sized load, pass at most three customer IDs as one comma-separated string:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/run_pipeline.py --start-date 2026-03-01 --end-date 2026-03-01 --customer-ids CUSTOMER_A,CUSTOMER_B,CUSTOMER_C
```

The parser trims whitespace and removes duplicate IDs. A supplied value that contains no
IDs is rejected. The loader also fails before committing dimensions when a requested ID is
not present in `customers.csv`.

The filter affects these tables:

| Table            | Filter behavior                                                     |
| ---------------- | ------------------------------------------------------------------- |
| `branches`       | Loads the complete shared catalog.                                  |
| `customers`      | Loads only requested customer IDs.                                  |
| `service_agents` | Loads the complete shared catalog.                                  |
| `products`       | Loads products owned by requested customers.                        |
| `transactions`   | Loads transactions owned by requested customers in the date window. |

Filtering reduces PostgreSQL writes, but the pipeline still scans the source CSV files to
find matching rows. EDA profiles customer-owned tables using the same filter.

## Artifact Names

Every pipeline run produces three JSON artifacts. One day uses one date in each name;
a range uses both inclusive endpoints.

| Run     | EDA profile                              | Scope manifest                              | Load manifest                              |
| ------- | ---------------------------------------- | ------------------------------------------- | ------------------------------------------ |
| One day | `eda_profile_2026-03-01.json`            | `scope_manifest_2026-03-01.json`            | `load_manifest_2026-03-01.json`            |
| Range   | `eda_profile_2026-03-01_2026-05-31.json` | `scope_manifest_2026-03-01_2026-05-31.json` | `load_manifest_2026-03-01_2026-05-31.json` |

Filtered runs append `customers-<count>-<hash>` to all three names. The stable hash is
derived from the normalized customer IDs, so rerunning the same customer set uses the same
artifacts while a different set does not overwrite them.

The load manifest is the audit record for one execution. It contains source checksums,
processed row counts, data adjustments, per-day outcomes, and failed-day details.
It also records `customer_filter.mode` and the normalized `customer_filter.customer_ids`
array. Verification always receives the exact manifest generated by the load stage and
scopes customer-owned count and orphan checks to those IDs.

## Transaction Behavior

Dimensions are committed before transaction partitions. Transactions are then processed
one day at a time:

- A successful day commits independently.
- A failed day rolls back only that day.
- Remaining days continue loading.
- The manifest status is `completed_with_errors` when any day fails.

Progress output includes:

```text
OK day=YYYY-MM-DD rows=N progress=X/Y
FAIL day=YYYY-MM-DD progress=X/Y error=...
Summary days_total=N days_loaded=N days_failed=N rows_loaded_total=N
```

## Idempotency

EDA and scope selection only read source files and overwrite artifacts with the same
date-derived name. Loading uses PostgreSQL upsert by primary key, so repeating a window
does not create duplicate rows. Existing rows with matching primary keys are updated.

## Seed Demo Users

After loading the selected customers, create their persisted login identities with one
shared password from `DEMO_USER_PASSWORD` (no default; outer whitespace is trimmed).
When `ADMIN_BOOTSTRAP_PASSWORD` is configured, customer seeding rejects the same
password before database access. Keep administrator and customer credentials in
separately named environment variables; do not place passwords in CLI arguments
or manifests. Administrator environment opt-in does not opt ingestion into seeding:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/seed_demo_users.py --customer-ids CUSTOMER_A,CUSTOMER_B,CUSTOMER_C
```

The command uses each customer's stored email and copies `first_name`/`last_name`
into the login identity's `name` on both creation and refresh. Each component is trimmed;
nonempty components are joined with one space. Partial names are retained, and missing
or blank components produce a null name when neither component is available. This code
mapping does not backfill existing identities; do not run refresh as a name-only repair,
since it also changes credentials, status, and token version.

Locale is inferred from `customers.country`:
`Brazil` or `Brasil` maps to `pt`, and every other country maps to `es`. Pass
`--locale es` or `--locale pt` only when every selected user needs the same explicit
override.

Apply the identity migrations before explicitly authorized seeding. Customer identities
use `CustomerUser` and the controlled customer role, not `User.customer_id`. New customer
identities are active; refresh explicitly activates only the selected customer identities,
preserves their subject and creation time, updates `updated_at`, and increments
`identity_version` to revoke existing tokens. Unselected users remain unchanged; normal
CSV ingestion does not activate or seed identities. The non-secret manifest includes
login `status`. Each
write records a secret-free `customer_migrate` audit event. Email collisions or invalid
associations roll back the entire seed without reassigning or promoting staff.

Users outside the selected list are unchanged. Unknown customer IDs are reported and
skipped. A non-secret manifest is written under `DATA_ARTIFACTS_DIR`.

[Identity](../identity/README.md) authenticates these persisted rows. The
[Responses BFF](../../responses-bff/README.md) forwards identity operations and has no
`DATABASE_URL`, ORM access, or copied password hashes.

## Monthly Product Snapshots

`product_monthly_snapshots` is an estimated operational projection built from the existing
PostgreSQL `products` and `transactions` rows. It does not rerun CSV ingestion. Each row
stores a product's reconstructed closing balance for one complete calendar month, that
month's approved transaction movement, and the current-balance anchor used by the
calculation.

The source stores every transaction amount as a positive value and does not provide a
debit/credit direction column. Profile the selected data before building snapshots:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/profile_transaction_semantics.py --customer-ids CUSTOMER_A,CUSTOMER_B
```

The profile reports aggregate statuses, types, signs, date coverage, and product ownership
or currency mismatches. The dataset has no external accounting source, signed amount,
transfer destination, or reversal reference. Digital events were also tested as a possible
cross-check, but they do not link to transactions by identifier, amount, or time.

The snapshot scripts therefore use this explicit default estimation policy:

| Source value                                    | Snapshot treatment                                   |
| ----------------------------------------------- | ---------------------------------------------------- |
| `Approved`                                      | Included; every other status has zero balance effect |
| `Deposit`                                       | Credit                                               |
| `Payment`, `Purchase`, `Transfer`, `Withdrawal` | Debit                                                |
| `Adjustment`                                    | Excluded because its direction is unknown            |

`Transfer` is treated as an outbound movement from the row's `product_id`. The policy is
stored on every snapshot. `excluded_approved_transaction_amount` reports the unsigned
adjustments in that month, while `balance_uncertainty_amount` accumulates excluded amounts
between the snapshot close and the current-balance anchor. The estimated balance range is
`closing_balance ± balance_uncertainty_amount`.

Apply the schema migration after the classification, specific database target and
write operation are approved. `upgrade head` also includes the identity revisions:
use the [explicit legacy-status migration command](#customer-and-identity-schema)
above rather than silently activating existing users.

Run a non-persisting calculation first. The default policy above requires no classification
arguments:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/build_monthly_snapshots.py --customer-ids CUSTOMER_A,CUSTOMER_B --dry-run
```

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/build_monthly_snapshots.py --customer-ids CUSTOMER_A,CUSTOMER_B
```

The default window begins in the first loaded transaction month and ends in the month
before the latest loaded transaction date. This excludes a partial current month. Use
first-of-month ISO dates with `--start-month` and `--end-month` to narrow the window.
Rebuilding is idempotent by `(product_id, snapshot_month)`.

Verify with the identical customer scope and optional month boundaries:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/verify_monthly_snapshots.py --customer-ids CUSTOMER_A,CUSTOMER_B
```

Use `--credit-types`, `--debit-types`, and `--excluded-types` together to override the
default. The three sets must be disjoint and classify every observed approved type.

Omitting `--customer-ids` requires the explicit `--allow-all-customers` switch because an
unscoped build may create snapshots for every product.

## Individual Commands

These commands are intended for diagnosis or rerunning one stage. Execute them in the
listed order and keep all dates and artifact paths aligned.

### 1. Create the EDA profile

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/eda_profile.py --source C:\Factored\data --output app/business-api/data/artifacts/eda_profile_2026-03-01.json --start-date 2026-03-01 --end-date 2026-03-01
```

### 2. Select and approve the scope

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/eda_select_scope.py --profile app/business-api/data/artifacts/eda_profile_2026-03-01.json --output app/business-api/data/artifacts/scope_manifest_2026-03-01.json --start-date 2026-03-01 --end-date 2026-03-01
```

Confirm that the scope JSON contains `"approved": true` before loading manually.

### 3. Load the approved window

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/load_scoped_data.py --source C:\Factored\data --manifest app/business-api/data/artifacts/load_manifest_2026-03-01.json --start-date 2026-03-01 --end-date 2026-03-01 --batch-size 50
```

### 4. Verify the same load manifest

Run verification only after the loader has created the manifest:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/verify_load.py --source C:\Factored\data --manifest app/business-api/data/artifacts/load_manifest_2026-03-01.json
```

If verification reports `FileNotFoundError`, the manifest path does not match the load
command or verification ran before loading completed.
