# Held-Out Evaluation: Transaction-Dispute Workflow

A fixed held-out scenario set, a baseline, and a runner that reports five named
metrics for the transaction-dispute support-case workflow: Safe Automated
Resolution, Containment, Escalation Quality, Unsafe Outcomes, and Operating
Efficiency (p50/p95 latency and cost per attempted/successful case).

## Files

- [`scenarios.json`](scenarios.json): 18 fixed cases (3 per category) across six
  categories: normal resolution, ambiguous/unsupported, human-required,
  adversarial, multilingual ambiguity, and workflow progression.
- [`run_held_out_eval.py`](run_held_out_eval.py): computes the baseline offline (no
  running services needed) and, when the local stack is up, drives the proposed
  system end to end through the Responses BFF.

## Status

- **Baseline (offline, reproducible now):**

  ```powershell
  python evals/run_held_out_eval.py --system baseline
  ```

  Sample size 18, fully offline. Result as of 2026-10-01: Safe Automated Resolution
  0.0 (the baseline never fast-tracks by design), Containment 0.667, Escalation
  Quality 1.0, Unsafe Outcomes 0/18. This is a "triage disabled" policy: every
  dispute either asks a clarifying question or escalates to the simulated human
  reviewer; security/ownership denials and pre-check rejections are unaffected
  because they sit outside the triage policy.

- **Proposed system (not yet run):** requires the full local stack (Account,
  Transaction, agent, BFF) already running, which this script does not start itself.
  Run it with:

  ```powershell
  python evals/run_held_out_eval.py --system proposed --bff-base-url http://localhost:8080
  ```

  Three scenarios (`NR-2`, and any future real-data case tagged
  `requires_dispute_window_fix: true`) will currently fail at the dispute-window
  pre-check regardless of agent behavior, because the loaded cohort's most recent
  transaction is already outside the live `DISPUTE_WINDOW_DAYS=90` check against the
  real clock. That is an expected, documented rejection, not an evaluation harness
  bug.

- **Classification caveat:** `_classify_response` in `run_held_out_eval.py` is a
  keyword heuristic over the agent's final text, not a judge model. Treat its labels
  as a first pass; the `detail` field in each result carries a text snippet so a human
  can confirm or correct the automatic label before citing these numbers anywhere
  outside this repo.

## Labeling discipline

Every number this script prints carries `sample_size` and `offline_or_simulated`.
Never present the baseline numbers above as a measured production result, and never
report the proposed-system numbers without first running them against the actual
live stack and manually spot-checking the `detail` transcripts.

## Against the deployed hosted agent (`home-banking-agent`)

The agent is actually deployed (`cd-hosted-agent.yaml` has run 6 times successfully;
current version 7 in the `foundry-development` Foundry project). Two ways to evaluate
it, one native and one custom, split by what each can actually authenticate as:

- **Native (`azd ai agent eval`)**: works today only for scenarios that don't need a
  signed customer identity. Tried against `app/agent/datasets/held-out-identity-independent.jsonl`
  (the three `ambiguous_unsupported` cases, `AU-1`/`AU-2`/`AU-3`) via
  `azd ai agent eval generate --agent home-banking-agent --dataset datasets/held-out-identity-independent.jsonl ...`
  then `azd ai agent eval run` (artifacts committed under `app/agent/eval.yaml`,
  `app/agent/datasets/`, `app/agent/evaluators/`). Result: **3 total, 0 passed, 0 failed,
  3 errored**. Root cause: every agent turn (not just tool calls) runs through
  `UserProfileProvider`, which calls `get_internal_principal()` unconditionally; with no
  `x-ms-user-identity` header, that raises before the agent produces any response.
  `azd ai agent invoke`/`eval` has no flag to inject a custom header (only
  `--user-isolation-key`/`--chat-isolation-key`, a different Foundry feature our agent
  doesn't use), so this errors on _every_ scenario, not just ones needing real customer
  data. Open the `Report:` URL the command prints for the raw per-row error if you want
  to confirm this directly in the portal.
- **Custom (`--target hosted`)**: `run_held_out_eval.py --system proposed --target hosted`
  bypasses the azd invoke path entirely and calls the deployed agent's `/responses`
  endpoint directly, self-minting the same `x-ms-user-identity` envelope the BFF would
  (`_sign_internal_identity`, mirroring `app/responses-bff/bff/internal_identity.py`
  exactly) and fetching an AAD token via the already-logged-in `az` CLI
  (`https://ai.azure.com` resource). This is what actually unblocks identity-dependent
  scenarios against the real hosted target.

  Requires `INTERNAL_IDENTITY_SECRET` (the same value `cd-hosted-agent.yaml` deployed)
  in your shell environment and an `az login` session with access to the
  `foundry-development` project. **Set the secret yourself and run this directly in
  your own terminal** — never paste it into chat or a shared terminal session:

  ```powershell
  $env:INTERNAL_IDENTITY_SECRET = "<value>"
  python evals/run_held_out_eval.py --system proposed --target hosted --only-category ambiguous_unsupported
  ```

  Rotating `INTERNAL_IDENTITY_SECRET` (the deployed value isn't saved anywhere locally,
  so it has to be regenerated and redeployed before this can run) only clears the
  identity blocker, not the separate DB-migration one. Breakdown of what it actually
  unlocks across the 18 scenarios:
  - **Clean, no DB dependency (5):** `AU-1`/`AU-2`/`AU-3` (no tool call needed at all)
    and `ML-2`/`ML-3` (response locale comes from the self-minted envelope's `locale`
    claim, never a DB lookup) — these produce real, meaningful pass/fail signal as soon
    as the secret works.
  - **Runs, but weak evidence until the DB has real data (3):** `AD-1`/`AD-2`/`AD-3`.
    With an empty deployed Postgres, any cross-customer lookup returns "not found"
    regardless of ownership enforcement, so a "denied" result here doesn't yet prove
    IDOR protection against a resource that actually exists for another customer.
  - **Still blocked either way (10):** `NR-1`/`NR-2`/`NR-3`, `HR-1`/`HR-2`/`HR-3`,
    `ML-1`, `WP-1`/`WP-2`/`WP-3` — all need a real, persisted transaction/product/
    customer row the agent can actually find and act on.

  `WP-*` also has a second, independent caveat: multi-turn continuation against the
  hosted endpoint is best-effort (it reuses whatever `conversation` value the response
  body returns, if any) and hasn't been validated yet.
