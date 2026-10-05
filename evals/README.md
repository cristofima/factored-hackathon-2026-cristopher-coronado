# Offline Evaluation and Synthetic Confirmation

## Current dispute contract

[dispute_cases.json](dispute_cases.json) is the 25-case **dispute-replay-v2**
development-exposed synthetic confirmation set, not untouched held-out evidence.
[dispute_freeze.json](dispute_freeze.json) freezes exact dataset bytes, canonical
expanded inputs, case count, and source dependencies. Dependency hashing normalizes
CRLF to LF for portability; dataset hashing remains exact. The scoped
`.gitattributes` rule keeps the frozen dataset checkout in LF on Windows too.
Freeze revision 3 records the reviewed `dispute-consent-v3` expansion for pre-intake
consent, production preview/location models, and asynchronous SDK tool invocation.
Revision 2 previously reviewed additive ADR 0009 projections and unexecuted defaults.
The 25 source scenarios, labels, dataset version, and exact dataset bytes remain
unchanged; canonical expanded inputs deliberately change to reflect the consent
contract. Workload or expansion changes require a new documented version/freeze.
Canonical expansion reads the dataset as UTF-8 before hashing compact, sorted-key
UTF-8 JSON; platform-default decoding is not equivalent for localized text.

Customer approval authorizes investigation only: every fraud-score band remains
IN_REVIEW. Low scores route to fast-track review, high scores escalate, and missing
scores require insufficient-signal review. Declining new intake creates no case;
declining a legacy pending case resolves it as withdrawn_by_customer.
Fixtures assert no posting, refund, credit, balance change, or product blocking.
Reviewer assignment is not a verdict. ADR 0009 approves production operator verdicts
and recorded financial effects; this investigation-only workload contains no simulated
assigned verdict and does not exercise those operations. Reassignment remains out of scope.

## Offline comparator and scoring

[run_dispute_replay.py](run_dispute_replay.py) implements finite-state intake from
customer turns and synthetic MCP replies, not expected labels. Separate transaction
confirmation precedes a read-only preview; explicit consent binds that preview to
acceptance directly into IN_REVIEW. Ambiguous consent creates no case. Legacy pending
cases retain their approval/decline path. Its narrow
en/es/pt grammar and dollar-prefixed amounts do not prove general language understanding.
[dispute_replay.py](dispute_replay.py) validates response models and checks complete
turns, ordered tool arguments/results, consent, selection, status grounding, and
unsupported actions. Financial-effect phrase checks are lexical, not semantic;
negation and mixed clauses still require human review.

Run from repository root using the existing agent uv environment:

```powershell
$env:PYTHONPATH = (Get-Location).Path
$env:OTEL_SDK_DISABLED = "true"
rtk proxy uv run --project app\agent --frozen --no-sync python -m pytest evals\tests -q --tb=short
rtk proxy uv run --project app\agent --frozen --no-sync python evals\run_dispute_replay.py --system baseline --timeout-seconds 10 --output evals\results\dispute-alignment-baseline.json
rtk proxy uv run --project app\agent --frozen --no-sync python evals\run_dispute_replay.py --rescore evals\results\dispute-alignment-baseline.json --output evals\results\dispute-alignment-rescored.json
```

Verified locally: **25 tests passed**, offline comparator **25/25 structured passes**,
and saved-evidence rescoring **25/25 passes**. These are synthetic results only.
The existing replay tests now bind paired fixtures to the current scorer and frozen
expanded inputs, reject missing/stale fingerprints, and check controlled nested
errors without retaining arbitrary exception text. The combined offline regression
command passed **57 tests** (32 existing replay tests and 25 alignment tests):

```powershell
rtk proxy uv run --project app\agent --frozen --no-sync python -m pytest app\agent\tests\test_dispute_replay.py app\agent\tests\test_mcp_replay.py evals\tests -q --tb=short
```

The comparator's 25/25 is synthetic comparator completion, not model-quality evidence.
These are historical session results recorded before subsequent operator/model-contract
changes, not a rerun against the current worktree. Validate the freeze before reuse.

## Current offline regression evidence

With freeze revision 3, the requested combined offline suites passed **77 tests**
with no warnings reported. The run used repository-root `PYTHONPATH` and
`OTEL_SDK_DISABLED=true`:

```powershell
rtk proxy uv run --project app\agent --frozen --no-sync python -m pytest evals\tests app\agent\tests\test_dispute_replay.py app\agent\tests\test_mcp_replay.py app\agent\tests\test_replay_summary.py -q --tb=short
```

This includes consent regressions and existing tamper/freeze tests. No source
scenario or label was changed for this repair. It is offline synthetic evidence,
not real-model, live authorization, PostgreSQL, browser, or hosted acceptance.

Historical results before Plan 11: after the reviewed projection fingerprint update and LF freeze restoration, the
following repository-root commands passed. Both used repository-root `PYTHONPATH`
and `OTEL_SDK_DISABLED=true`:

| Command                                                                                                                                                             | Result                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `rtk proxy uv run --directory app\agent python -m pytest tests\test_hosted_workflow.py tests\test_dispute_replay.py ..\..\evals\tests\test_offline_alignment.py -q` | 91 passed, 24 existing Azure SDK deprecation warnings  |
| `rtk proxy uv run --directory app\agent python -m pytest tests ..\..\evals\tests -q --tb=short`                                                                     | 134 passed, 24 existing Azure SDK deprecation warnings |

These checks cover instruction contracts, mocked workflow behavior and synthetic
replay/freeze guards. They do not establish real-model discovery, semantic quality,
locale correctness, service authorization, financial settlement or hosted identity
transport. No billable inference or cloud evaluation was run for this continuation.

## Consultation safeguards and session evidence

Existing-case inquiries are read-only. Triage routes case lists, status, timelines,
and follow-ups to Transaction. Use customer/tool-supplied IDs, request selection for
ambiguous references rather than choosing the newest case, refresh detail on status
follow-ups, and read timeline events for event questions. Empty lists are truthful;
missing and foreign cases remain equivalently unavailable. Consent or IN_REVIEW
never establishes operator takeover or a verdict. User-facing prose follows the
signed locale; underscore/hyphen machine codes remain unchanged.

Historical session validation recorded:

| Focused command from repository root                                                                          | Result    | Evidence boundary                                                |
| ------------------------------------------------------------------------------------------------------------- | --------- | ---------------------------------------------------------------- |
| `rtk proxy uv run --directory app\responses-bff pytest tests\test_responses.py -q`                            | 23 passed | Mock Identity/upstream continuation and staff-denial regressions |
| `rtk proxy uv run --directory app\agent python -m pytest tests\test_hosted_workflow.py -q`                    | 16 passed | Instruction-contract and mocked workflow checks                  |
| `rtk proxy uv run --directory app\business-api\transaction python -m pytest tests\test_dispute_service.py -q` | 43 passed | Seeded SQLite lifecycle/ownership checks                         |

The agent command used repository-root PYTHONPATH and OTEL_SDK_DISABLED=true.
Continuation tests re-introspected Identity and stopped revoked/version/role changes
or outages before a second agent request; operator/admin denial made zero agent
upstream calls. Instruction assertions prove safeguards are present, not real-model
compliance. These results are not live service/authz, PostgreSQL parity, browser,
locale-quality, or hosted-transport acceptance; no such run was performed for this
documentation update.

[Hosted Agent CI](../.github/workflows/ci-hosted-agent.yml) configures offline dispute
tests, comparator execution, separate rescoring artifacts, and 14-day retention.
Configuration is not proof of a successful CI run.

## Evidence and paired reporting

Default artifact names include timestamp/UUID. Occupied explicit paths are redirected
to unused names, including JSON/Markdown/JUnit sibling collisions. Use the printed
saved path rather than assuming overwrite. Complete redacted answers, SDK responses,
stream updates, ordered calls, pending turns, unused replies, timeout evidence, and
nested controlled failures are retained. Credential-like keys and token/secret
strings are removed; nonsecret text is not truncated. Only the fixed nonproduction
`SYNTHETIC-PREVIEW-TOKEN` marker is retained in `previewToken`/`preview_token` fields
so saved synthetic evidence preserves consent binding during rescoring. Arbitrary
preview capabilities remain redacted. Inspect redaction before sharing.

Saved proposed evidence supports offline --rescore and --compare-baseline. Pairing
requires identical frozen expanded inputs, dataset hash, case IDs/locales, and
current scorer fingerprint. Reports include model, prompt, comparator, contract,
and runtime metadata. Structured wins/ties/losses and failures are reported; a tie
can mean both failed. Only completed valid nonfailed timings enter percentiles.
Missing, negative, Boolean, NaN/infinite, incomplete, or failed timing is excluded,
not zero. No prices are assumed; cost and safe-resolution economics are unavailable.
Pairing does not establish semantics, locale quality, real authorization, persisted
effects, or improvement over human operations.

Proposed dispute replay calls a real model through in-memory MCP sessions and needs
explicit endpoint/model and billable-run authorization. No model run was executed
for this offline alignment.

## Identity fixture boundaries

Synthetic customer metadata carries role=customer and strict positive integer
identity_version=1. It is not a JWT. The signed agent envelope contains only sub,
customer_id, email, and locale; its v1 format is independent of JWT identity version.
Production JWTs additionally require role/version, issuer, audience, expiry, and
introspection checks. Offline fixtures prove no crypto, revocation/introspection,
role enforcement, service ownership, or BFF/hosted identity transport.

## Isolated MCP replay

[mcp_replay.py](mcp_replay.py), [run_mcp_replay.py](run_mcp_replay.py), and
[replay_cases.json](replay_cases.json) exercise three synthetic balance, canned-denial,
and empty-transaction protocol cases using the production workflow and real model.
They do not test disputes or real service authorization. Caller-supplied sessions
stay separate from production HTTP/header providers. Full evidence and controlled
failures are retained; behavioral review is separate from protocol passes.
The supplied-number cases expect direct resource lookups, not preliminary account
listing. The denial case is an ordinary balance request with a canned tool ownership
denial; it does not require a tool call for a prompt that can safely be refused outright.

The runner requires `--model` as the base deployment and accepts optional
`--triage-model`, `--account-model`, and `--transaction-model` overrides. Each omitted
or empty override independently falls back to the base deployment, matching production.
Clients are reused when participants share a deployment. Reports retain `model` and
record the effective deployments in `participant_models`.

CI reads `MODEL_DEPLOYMENT_NAME` and the optional Development environment variables
`TRIAGE_MODEL_DEPLOYMENT_NAME`, `ACCOUNT_MODEL_DEPLOYMENT_NAME`, and
`TRANSACTION_MODEL_DEPLOYMENT_NAME`, forwarding them to those flags. These are
existing model deployment names, not agent names; replay does not provision models.

Warnings about missing outgoing handoffs for AccountAgent and
TransactionHistoryAgent reflect the intentional terminal-specialist topology. They
are not themselves a protocol failure; unexpected calls or unused replies still fail
replay and report validation. Prompt contracts and offline tests do not guarantee
real-model compliance; a separately authorized CI replay confirms runtime behavior.

## PR smoke check

[replay_summary.py](replay_summary.py) rejects missing/partial reports, duplicate
cases, protocol errors, unused replies, and missing transcript/answer evidence.
CI uses Development OIDC for same-repository PRs to main/develop, retains 14-day
artifacts, and publishes controlled statuses in a persistent PR comment. Fork model
replay is explicitly not executed. This is not a dispute quality/authz gate.
[CI run 37264970360](https://github.com/cristofima/factored-hackathon-2026-cristopher-coronado/actions/runs/37264970360)
passed agent build/tests, PR/OIDC/real-model MCP protocol smoke, report validation,
evidence upload and PR reporting at commit `ee40605859f3ae7c2e047182025c8c304bead418`.
Its Dispute Replay job also passed offline alignment regressions, deterministic
comparator and saved-evidence rescoring checks. These offline checks do not establish
real-model dispute quality, semantics, real ownership, business approval, persisted
financial effects or hosted identity transport.
No runner creates a remote Foundry evaluation; local display names are not remote IDs.

## Historical diagnostics

[scenarios.json](scenarios.json) preserves 18 **historical obsolete-policy** diagnostic
definitions. [run_held_out_eval.py](run_held_out_eval.py) keeps its label-derived
baseline and keyword classifier for historical diagnostics only. Obsolete automatic
resolution labels are not current acceptance expectations. Full redacted per-turn
responses are retained, and execution continues after controlled failures.
Local live mode requires an explicitly supplied password and an existing BFF stack;
hosted direct mode is diagnostic, not browser/BFF topology acceptance. Neither live
mode ran for this alignment. Historical numbers are not v2 results.

## Remaining acceptance gates

- Assigned-operator adjudication and financial effects are approved by ADR 0009,
  but the frozen investigation-only replay does not exercise or establish their acceptance.
- Real-model paired disputes, consultation behavior, semantic/locale review, and variability.
- Live JWT role/version/introspection and real ownership/authz acceptance, separate
  from the mocked/seeded regression results above.
- Persisted case/event parity; financial effects are not implemented by these fixtures.
- Browser/BFF and hosted identity/continuation evidence.
- Untouched external confirmation workload and priced usage/cost evidence.
