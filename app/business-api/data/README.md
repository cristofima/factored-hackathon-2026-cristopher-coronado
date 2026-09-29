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

The `users` table is not populated by this pipeline. Application identities are managed
separately by the authentication workstream.

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
```

| Variable             | Purpose                                                                           |
| -------------------- | --------------------------------------------------------------------------------- |
| `DATABASE_URL`       | PostgreSQL SQLAlchemy connection URL.                                             |
| `DATA_SOURCE_DIR`    | Directory containing dimension CSVs and the partitioned `transactions` directory. |
| `DATA_ARTIFACTS_DIR` | Directory for EDA profiles and scope manifests.                                   |
| `DATA_MANIFEST_DIR`  | Directory for load manifests. This is a directory, not a JSON filename.           |

The orchestrator derives a new manifest filename from the requested window. A fixed
`DATA_MANIFEST_PATH` is intentionally not used because it would overwrite the evidence
from a previous run.

Always pass the environment file explicitly to `uv`; it is ignored by Git and is not
loaded automatically.

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
