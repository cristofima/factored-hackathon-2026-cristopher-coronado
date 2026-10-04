# Competitor Research

The original 2026-10-01 review covered nine repositories through their README and
other documentation. The expansion below adds eight repositories using **README
files only**, without inspecting competitor source code or executing their systems.
Capabilities and metrics in those historical passes are team-reported documentation
claims, not independent implementation, security, production, or evaluation verification.
The separate [bounded source review](#bounded-source-review-dispute-rule-engines)
below verifies selected implementation bodies without executing competitor systems.

The current inventory at `C:\Factored\competencia` contains 13 directories: five from
the original review and eight new ones. Retaining the four historical entries no
longer present locally gives **17 distinct repositories across both passes**. The
historical findings below have not been revalidated in this expansion.

The new comparisons use the effective-actions plan's acceptance boundaries: **Lane A**
is truthful, customer-owned, versioned evidence and an authenticated human reviewer
handoff; **Lane B** is optional financial/protection execution requiring separate
policy and migration approval. Customer consent, a human verdict, and an executed
effect are different events. Our Identity implementation does not establish accepted
reviewer integration, and neither case-status text nor synthetic replay proves a
credit, balance change, or card block. No competitor pattern changes those boundaries.

## Original review: nine repositories

| Repo                                      | Chosen workflow                                                                                        | Same domain as ours (transaction disputes)? |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------- |
| `factored-hackathon-2026-aureliano-main`  | Credit eligibility + predictive risk                                                                   | No                                          |
| `factored-hackathon-2026-CRUDmakers-main` | General transactional assistant (balances, payments, Pix); disputes only as one escalation reason code | Partial                                     |
| `factored-hackathon-2026-Datti-main`      | "Expediente Vivo": unrecognized-charge / incorrect-charge disputes with analyst lanes                  | Yes                                         |
| `factored-hackathon-2026-jagusgelos-main` | Transaction-dispute resolution ("Cargo no reconocido" is 90.5% of their complaint volume)              | Yes                                         |
| `factored-hackathon-2026-jdlr-main`       | Dispute-matcher + credit eligibility on real AWS infrastructure                                        | Yes                                         |
| `factored-hackathon-2026-noema-main`      | Credit eligibility (disputes explicitly rejected in their own ADR-0001)                                | No                                          |
| `factored-hackathon-2026-sofia-main`      | Dispute triage with a 7-layer LangGraph agent                                                          | Yes                                         |
| `factored-hackathon-2026-svengineer-main` | Dispute intake/triage with explicit fraud/ambiguous/high-risk archetypes                               | Yes                                         |
| `project-hackathon-factored-2026-main`    | Credit eligibility on Azure Function App, LangGraph                                                    | No                                          |

Five of the original nine repositories selected a dispute-related track; CRUDmakers
had partial overlap. These counts describe that historical sample only, not the
current directory inventory or the complete competition.

## Historical per-team findings

### aureliano — Credit eligibility

- System 1/System 2 split: a fast triage/safety layer (Jev) decides escalation, a
  second model (Claude Sonnet 5.5) drafts prose but never computes numbers.
- A number verifier blocks any figure in a response that isn't traceable to a tool
  output.
- Data pipeline: DuckDB bronze/silver layers from S3, DVC-versioned, schema contracts
  in `contracts/tables.yml`.
- Risk model: features snapshotted at time _t_, label `days_past_due > 30` at _t+3_,
  split by customer and time, benchmarked against a credit-score-only baseline.
- Evaluation: ~60 scripted ES/PT scenarios, metrics for safe-automated/containment/
  escalation-quality/unsafe-outcomes, latency p50/p95, broken down by language/segment.

### CRUDmakers — Transactional assistant

- LangGraph orchestration, policy encoded in `policy/rules.py`, never in the prompt.
- Dedicated reason codes for handoff (`UNRECOGNIZED_CHARGE`, `FRAUD_RISK`,
  `AMOUNT_OVER_LIMIT`, etc.) plus a `HND-<ref>` case reference shared with the human
  agent.
- A trained route classifier (sentence-transformers embeddings + logistic regression)
  trained on 2023-2025 data, tested on 2026 (no leakage), predicting
  `direct_handoff` / `refusal` / `clarify` / `answer`.
- Milestone M5 evaluation: 262 frozen ES/PT cases, 99.3% safe resolution, 0 unsafe
  outcomes across 786 cases, compared against two baselines (keyword bot, tool-loop
  without policy).
- Mock bank service with a dry-run → preview → confirm → execute → read-back-verify
  payment flow; the number the customer confirms is the preview, not LLM prose.

### Datti — "Expediente Vivo"

- Case states: `open → investigating → awaiting_analyst → notified → closed` (plus
  `well_resolved_in_contact` / `handed_off`), routed into three lanes (A: resolve now,
  B: open case with SLA, C: hand off to a human) by YAML rules, not the LLM.
- An asynchronous "investigator" agent (G2) produces a cited report and a hypothesis
  (`fraud|forgotten_purchase|unfamiliar_merchant_name|duplicate|fee_error|
pending_reversal`) for lane-B money cases; a human analyst approves/edits/rejects it
  before anything is finalized ("approved by a person; no money moves in this demo").
- M1 (transaction ranker, LambdaRank), M2 (calibrated intent classifier, 9 classes),
  M3 (risk/fraud feature scoring) feed the lane decision; `fraud_score` from the
  dataset is one of the inputs.
- Full JSONL trace of every step (actor, latency, tokens, cost) for audit and future
  learning.
- Evaluation plan: planted scenarios over real transactions plus 150 team-written test
  messages, baseline = their own v1.4 rules-only system.

### jagusgelos — Dispute resolution

- Deterministic policy guard (`app/policy.py::evaluate_case`) is the only place that
  can authorize a credit or an escalation; a priority classifier (chronological split,
  dated 2026-01-06, no leakage) can only _add_ an escalation reason, never auto-resolve
  or authorize credit on its own.
- Case state machine: `confirming → awaiting_explanation → [resolved_auto |
escalated]`, escalation reachable from any state.
- Structured handoff: request summary, verified facts, customer-reported reason,
  policy reasons (closed set of 9 values), actions taken, evidence, open questions
  (never a raw transcript).
- `build_prompt_context` is the only path into any prompt, enforced by a conformance
  test that plants PII sentinels and checks they never leak.
- Evaluation: 29 scenarios (6 workflows × ES/PT + 7 adversarial + 3×2 parity checks),
  100+ unit tests including adversarial/policy-abuse cases, deterministic Anthropic
  mocking for reproducibility offline.

### jdlr — Dispute matcher + eligibility (AWS)

- Real infrastructure: Terraform-provisioned Step Functions Express orchestrating
  separate Lambdas per agent stage (`conversation-agent`, `policy-agent`,
  `transaction-agent`/`retrieval-agent`, `verification-agent`, `escalation-agent`),
  each with least-privilege IAM.
- Decision model: deterministic YAML policy (`policies.yaml`) evaluated alongside a
  Bedrock guardrail; the more conservative of the two wins (`AUTO < CLARIFY <
ESCALATE`).
- Transaction matcher: baseline is substring-merchant-match + amount tolerance;
  proposed model adds Bedrock embedding similarity + date proximity. Evaluated on 102
  held-out synthetic cases: Recall@1 66.7% → 95.1%, MRR 0.828 → 0.972, 100% precision-
  when-confident in both.
- `fraud_score` reused as-is from the dataset, explicitly documented as "no new
  training, this signal already existed at authorization time."
- "Decide stage" evaluation: 17 held-out cases, real measured cost per case ($0.0078).
- A single canonical TypeScript contracts package (`packages/shared/src/contracts/`)
  is the source of truth for every agent's I/O schema; markdown docs are kept in sync
  with it, not the other way around.
- Explicit, honest limitations section: mock demo data, synthetic eval set, no fraud
  fine-tuning attempted, real human-agent cost not modeled.

### noema — Credit eligibility

- Explicitly rejected transaction disputes in `ADR-0001` as "too agentic," where a
  trained component would be decorative.
- Pivoted a planned repayment-capacity model into a published data-quality finding
  (83% of transactions in the raw dataset occur before the associated account
  existed) rather than training on data they judged too corrupted to trust.
- Deterministic eligibility engine (`policies/eligibility_v1.yaml` + `engine.py`),
  58 rule-engine tests with no LLM involved; a `GroundingChecker` verifies every number
  in a response traces back to the engine's output.
- Mandatory read-back verification before confirming any action to the customer.

### sofia — Dispute triage

- Explicit 7-layer graph: `PURPOSE → SENSE → INTERPRET → DECIDE → ORCHESTRATE →
GOVERN → LEARN`, framed as a state machine rather than a free-form ReAct loop.
- A separately trained intent router (own `ml/` package) feeds the `INTERPRET` layer,
  evaluated on a 30-case ES/PT dev set across 5 difficulty levels.
- Rules-only baseline vs. Gemini-backed proposed system with an explicit fallback
  chain and a regression gate (`MET-01..06`) that must pass before merging.
- Full Langfuse tracing per conversation (`trace_id`, `session_id`, `prompt_version`).

### svengineer — Dispute intake/triage

- Three explicit archetypes drive the policy: clear fraud (`is_fraud=True` and
  `fraud_score >= 0.85`) auto-resolves, ambiguous (score 0.40-0.85 or missing fields)
  asks for clarification, high-risk (critical/high priority, SLA breach, amount over
  threshold) escalates.
- Same `understand → decide → act → verify → escalate` graph shape as the hackathon
  brief's own diagram, implemented explicitly rather than left implicit in an LLM loop.
- Versioned JSON handoff contract (`extra="forbid"`) that never includes a raw
  transcript.
- Policy lives in `backend/app/policy/rules.py`, never in the LLM (their own ADR-002).
- Baseline (TF-IDF + logistic regression) vs proposed (embeddings/LLM) classifier
  already run in their first sprint, ahead of most other teams reviewed.

### project-hackathon-factored-2026-main — Credit eligibility

- LangGraph graph compiled to run on Azure Function App Flex Consumption (not an
  agent framework's own hosting), with MLflow + App Insights tracing every decision
  back to a `trace_id`/`prompt_version`/policy rule.
- A novel evaluation metric for _non-agency_: an action confusion matrix across
  Act/Abstain/Paired-Accuracy, containment rate, unresolved-rate, false-positive rate.
- Pre-scoring via a LightGBM model served on Databricks Model Serving (scale-to-zero),
  explicitly an input signal, never the decision-maker.

## README-only expansion: eight new repositories

Source links below are local README snapshots, not public repository URLs. Line
references identify the evidence read during this pass. Missing documentation is
not proof that a capability is absent. Similar wording in Robinson-Miranda and
The Trident does not establish independent implementations or results.

### AIDO

Source: [root README](../competencia/factored-hackathon-2026-AIDO-main/factored-hackathon-2026-AIDO-main/README.md),
lines 1–28, 36–80.

- **Documented:** Account/transaction inquiries and dispute intake in Spanish and
  Portuguese. The model interprets/drafts; deterministic policy controls actions.
  Provenance-typed values distinguish grounded facts, and the model cannot select
  the source or disputed charge. Session identity and database facts constrain access.
- **Consent/effects:** Single-use nonce confirmation outside chat; typed agreement
  alone is insufficient. No refund, reversal, blocking, approval or money movement.
- **Evaluation:** Approximately 200 multi-turn scenarios are planned, with
  deterministic checks and a human-calibrated LLM judge (target κ ≥ 0.6). The README
  explicitly reports no results yet; planned counts and audit numbers are not scores.
- **Lane A comparison:** Adopt typed evidence and explicit missing facts. A structured
  handoff is relevant, but the README does not establish our authenticated reviewer
  verdict, evidence-version guard or operational queue acceptance.
- **Lane B comparison:** Its no-money boundary matches a safe evidence-only lane;
  it supplies no financial-execution evidence or reason to expand our scope.

### Calvino

Sources: [root README](../competencia/factored-hackathon-2026-calvino-main/factored-hackathon-2026-calvino-main/README.md),
lines 8–35; [baseline README](../competencia/factored-hackathon-2026-calvino-main/factored-hackathon-2026-calvino-main/reports/baseline/README.md),
lines 5–21, 27, 43–47.

- **Documented:** Stuck-payment explanation, clarification, permitted simulated
  action, investigation and follow-up. Models suggest, versioned policy decides,
  people approve important steps. Dispute/fraud cases go to a person; no money moves.
- **Evidence/evaluation:** Verified replies and case files are described, but source
  provenance and customer-resource authorization are not established by these READMEs.
  No system results are reported. Baseline counts (686,296 interactions, 67,095
  complaints, 15,363 complaint-resolution observations) characterize data, not agent
  test cases. Reports include excluded-null counts and a `small_n` flag below 30.
- **Lane A comparison:** Reuse versioned policy and transparent denominator/null
  reporting. Complaint-resolution days are not measured reviewer handling-time savings.
  Human escalation alone does not prove final-verdict permissions or stale-case guards.
- **Lane B comparison:** Simulated policy-permitted actions cannot demonstrate atomic
  posting, balance effects, verified card relationships or financial authorization.

### DataBank SV / Harbor Desk

Source: [root README](../competencia/factored-hackathon-2026-databank_sv-main/factored-hackathon-2026-databank_sv-main/README.md),
lines 1–5, 24–26, 118, 155–182.

- **Documented:** One-charge dispute workflow, verified-facts packet, masked data,
  audit trail and HIGH/REVIEW/LOW routing. Missing features route to REVIEW. The LLM
  does not decide outcomes; a human sends the reply. Fraud labels are excluded from
  application inputs. Synthetic duplicate and injection demos are described.
- **Consent/effects:** HIGH routing can offer card blocking after confirmation;
  the assistant never moves money. README descriptions do not independently verify
  the block or its authorized product relationship.
- **Evaluation/identity:** No headline numeric system score is established by the
  reviewed root README. Demo descriptions and links to evaluation documents are not
  executed evidence. Customer ownership enforcement is not established here.
- **Lane A comparison:** Reuse missing-signal escalation, masked evidence and explicit
  input-label separation. Human-authored replies are not necessarily persisted,
  authorized approve/reject verdicts with rationale and evidence version.
- **Lane B comparison:** Confirmation is necessary but insufficient for blocking.
  Keep our policy/migration, relationship, idempotency and atomic-audit gates open.

### Fabian Abarca (development)

Source: [root README](../competencia/factored-hackathon-2026-fabian-abarca-development/factored-hackathon-2026-fabian-abarca-development/README.md),
lines 20–47, 99–143.

- **Documented:** An agent console separates verified facts (source table/record ID),
  unverified customer claims, actions, open questions, reasons and model signals.
  Only a human sends the reply. Database object owners, grants and application/admin
  roles are described, alongside access auditing.
- **Evaluation:** Seeded `SEED-` scenarios and a harness specifying three system runs,
  a disconnected run and a baseline. Policy-derived labels are documented; no final
  performance result is established by this README. Such labels alone cannot validate
  independent semantic quality or reviewer decisions.
- **Lane A comparison:** The source-linked console is a useful evidence-packet pattern.
  Database grant ownership is not customer-resource authorization; neither grants nor
  human reply authorship proves reviewer verdict authority. Our existing Identity
  roles still need scoped reviewer-service enforcement and operational acceptance.
- **Lane B comparison:** Customer consent, financial authority and persisted financial
  effects are not established. Do not infer settlement from a console or audit log.

### Proof of One

Source: [root README](../competencia/factored-hackathon-2026-proof-of-one-main/factored-hackathon-2026-proof-of-one-main/README.md),
lines 7–9, 23–25, 31, 34, 48.

- **Documented:** A deterministic pre-LLM freeze candidate with ANSWER/CLARIFY/
  ABSTAIN/ESCALATE outcomes. The judge-facing runtime has no live LLM. The model
  cannot control authenticated customer identity or rebind it. Ticket persistence
  is re-read before reporting escalation; banking dependency failure is fail-closed.
- **Evaluation:** A private 200-case conformance/safety suite and 100-case development
  pool are described. The 32-case realistic-language set is explicitly inadmissible
  for uplift claims. A supervised fraud-risk experiment failed its usefulness gate
  and was not deployed. Counts are not independent verification or paired-model results.
- **Lane A comparison:** Adopt fail-closed dependency handling and verified handoff
  delivery. Deterministic conformance and ticket creation do not establish semantic
  quality, evidence versioning or an authorized final human verdict.
- **Lane B comparison:** Ticket verification is not ledger verification. No README
  evidence establishes our atomic posting/balance/event or ingestion-protection gates.

### Robinson-Miranda

Source: [root README](../competencia/factored-hackathon-2026-Robinson-Miranda-main/factored-hackathon-2026-Robinson-Miranda-main/README.md),
lines 3, 7–9, 16.

- **Documented:** AI-first disputed-card intake on synthetic data. The LLM reads and
  drafts; a deterministic fact checker and policy control decisions/actions, with
  a rules/template fallback. Exact pending-action confirmation precedes dispute or
  block actions; actions are re-read, and mismatches are sent to an analyst.
- **Evaluation/limitations:** The README says `make eval` runs 25 golden cases with
  none skipped. This pass did not execute them or verify a score. The prototype is
  in progress; analyst dossiers and the priority queue are explicitly not built.
  Customer/session ownership is not established by the root README.
- **Lane A comparison:** Useful exact-action confirmation and readback discipline,
  but its explicit unfinished queue reinforces our separate reviewer-delivery gate.
  A mismatch transfer is not a recorded human adjudication.
- **Lane B comparison:** Synthetic block/dispute actions do not establish financial
  posting, a safe card-account relationship or atomic/idempotent execution.

### Sentinel Engine

Source: [root README](../competencia/factored-hackathon-2026-sentinel-engine-main/factored-hackathon-2026-sentinel-engine-main/README.md),
lines 7, 13, 18–19, 72–83, 96–102.

- **Documented:** Understand→Decide→Act→Verify→Escalate. AI labels intent; policy,
  confirmation, sessions, execution and verification remain in code, with a baseline
  fallback. Customer identifiers are masked before model calls. Advisor tickets carry
  reasons, summaries, verified facts and attempted actions.
- **Evaluation:** README-reported requirements coverage is 57 total: 41 done,
  nine in progress, seven pending. Intent accuracy is 0.98 versus 0.54 baseline
  on a sealed set of 280. A resolution simulation reports 16/56 across 14 situations,
  zero unsafe outcomes and zero missed transfers. These are different denominators
  and tasks, not one end-to-end score. The live demo predates later changes.
- **Lane A comparison:** Reuse the explicit handoff schema and failure fallback.
  Intent accuracy cannot prove safe resolution, authorization or locale fidelity.
  Tickets/masking do not establish scoped reviewer verdicts, evidence-version guards
  or our required ownership evaluation.
- **Lane B comparison:** Action verification is documented, but ledger/balance effects
  and our financial invariants are not established by the README.

### The Trident

Sources: [root README](../competencia/factored-hackathon-2026-the-trident-main/factored-hackathon-2026-the-trident-main/README.md),
lines 3–9, 14–18; [evaluation README](../competencia/factored-hackathon-2026-the-trident-main/factored-hackathon-2026-the-trident-main/eval/README.md),
lines 1–11.

- **Documented:** The five-stage loop uses deterministic policy, token scopes and
  customer flags. LLM understanding/verification cannot replace policy authority.
  Exact-action customer confirmation and database readback precede a success claim;
  mismatches escalate to an analyst. Human escalation is described as closed-loop.
- **Evaluation/limitations:** The root reports 25 golden cases, none skipped, but
  autonomy is in progress and analyst dossiers/priority queue are unbuilt. The
  evaluation README separates development-authored cases (overfitting risk) from
  temporal held-out intent labels and frozen prompts. No run was verified in this pass.
  Token-scope wording does not establish customer-resource ownership enforcement.
- **Lane A comparison:** Reuse exact confirmation, verification and development versus
  held-out separation. It does not establish versioned evidence, a completed queue
  or a persisted authorized final reviewer verdict.
- **Lane B comparison:** Registration/blocking descriptions are not proof of atomic
  financial postings, balance mutations, reversal links or ingestion protection.

## Cross-team observations and comparison limits

1. **Deterministic authorization is a recurring documented pattern, not proof of
   human adjudication.** Historical dispute teams describe policy-controlled
   clarify/escalate/auto-resolve paths. Our deterministic ownership checks and score
   routing are existing controls, but the improved target requires a real authorized
   human's final verdict, rationale and evidence version. Routing or customer consent
   cannot establish that boundary.
2. **Evaluation artifacts have different meanings.** Historical counts include
   CRUDmakers' 262 cases, jagusgelos' 29 scenarios, sofia's 30 cases and jdlr's
   102-case matcher/17-case decide evaluation. Do not compare subtask accuracy,
   offline conformance and end-to-end safe resolution as one score. Our 18 held-out
   definitions/offline baseline and 25 development-exposed dispute replay cases are
   distinct assets; paired real-model, semantic/locale, reviewer and effect acceptance
   remain separate gates. See [the evaluation guide](evals/README.md).
3. **Structured handoff is more than a timeline.** Named handoff contracts in the
   original sample separate verified facts, customer statements, attempted actions,
   evidence and unresolved questions. Our target additionally needs source timestamps,
   evidence versioning, missing/contradictory facts and authorized queue delivery.
4. **Fraud-model claims need narrower attribution.** Several historical teams reuse
   pre-existing scores or train intent/ranking components. This is not evidence that
   no competitor trains a fraud model. The new findings above include an explicitly
   rejected supervised fraud-risk experiment. In our evaluated inputs, keep `is_fraud`
   as an offline oracle, missing signals missing, and historical features strictly
   prior to the disputed transaction.
5. **Documentation cannot close operational gates.** A confirmed action, ticket,
   policy outcome or claimed test pass does not prove posting/balance/card effects,
   reviewer permissions, stale-evidence/concurrency protection or live deployment.
   No newly reviewed README establishes our complete Lane A or Lane B acceptance.

## Bounded source review: dispute rule engines

This pass inspected six local repositories: five implemented policy engines and
sofia's agent-side eligibility consumer. Sofia's services policy/routes packages
contain docstrings only, and its service entry point exposes health only; the real
SIM eligibility engine was **not established** in this checkout. Its fake backend
explicitly identifies itself as a test substitute, not that service. This corrects
any reading of the earlier README comparison as verified SIM implementation.

**Current approval is operator queue and claim only.** The earlier Lane A verdict,
evidence-version adjudication and reassignment recommendations remain future work,
not authorization. No competitor thresholds, labels, clocks or automatic outcomes
become our policy. This pass changes no application behavior or acceptance status.

### Actual decision boundaries

| Repository | Implemented boundary and missing-signal behavior | Meaning and limitation |
| --- | --- | --- |
| jagusgelos | Screening checks status, age, amount/conversion, score, history and exposure; later evidence checks distinguish unrecognized charges and duplicate pairs. Missing/high score, unknown conversion or missing required history escalate. Classifier escalation is additive and cannot rescue failed rules. | Screening `AUTO_RESOLVE` permits further workflow, not immediate credit. Separate evidence checks and state transitions matter; duplicate-pair identity is not a human legitimacy verdict. |
| jdlr | YAML evaluator accumulates matches with `ESCALATE > CLARIFY > AUTO`; no match escalates. Dispute rules escalate suspected fraud or no match, clarify ambiguous candidates, and permit AUTO only for found transaction plus explicit false fraud suspicion. Model guardrail can only move to a more conservative outcome. | The verifier derives suspicion directly from `tx.is_fraud === true` and returns a simulated `productBlocked` Boolean. This reuses a dataset label and is not independent investigation or verified card blocking. Generic `neq`/`not_in` and negation can match absent fields: the evaluator's broad missing-field comment is not universal. |
| svengineer | Escalation for priority/amount/SLA/status outranks clarify/auto. Missing amount/reference or ambiguous fraud signals clarify. Pure policy AUTO requires sufficient facts, truthy fraud label and normalized score at least 0.85. Actual graph caller additionally escalates unavailable verification evidence and verified low-score non-fraud, and demotes AUTO on blocking ambiguity. | Priority is routing, not eligibility or legitimacy. Pure-function output alone overstates the graph's final decision. Using `is_fraud` for automatic outcomes is unsuitable for our reviewer boundary. |
| AIDO | Rules return action, sorted reason IDs and policy version. Risk/provenance/human-request gates escalate; missing targets clarify. Dispute checks include count, amount, score/null, type/status, invalid/future/old date, existing dispute and repeat complaint. Passing returns `confirm`. | Confirmation is not execution or adjudication. Config explicitly uses synthetic policy and a fixed dataset clock; provenance tags do not prove ownership. Pending-action consumption/persistence was not verified. |
| DataBank SV | HIGH score wins before Pending/Reversed out-of-scope routing. Missing features and model failures route to REVIEW with fallback/version flags; missing/NaN scores do not become HIGH. Rule reconciliation prevents unsupported model HIGH or fallback LOW. | Versions identify rules/model/fallback, not a fresh evidence snapshot. Routing has a state/action map, but does not independently establish legitimacy or authenticated human ownership. |
| sofia | Agent calls eligibility endpoint, requires a selected transaction, preserves rule facts, denies cross-customer signals and escalates human requests/kill switch. Confirmation checks prior AUTO eligibility, expiry and a subsequent turn. | Implemented consumer/contract, not verified service rule engine. No claim that SIM rules, single-use action tokens or production persistence are implemented from these files. |

The engines disagree materially: jagusgelos screens low-risk cases for further
evidence, svengineer permits clear labeled-fraud AUTO in its pure policy, jdlr
permits found/non-fraud AUTO, and DataBank prioritizes HIGH before status exclusion.
Those differences demonstrate distinct synthetic policies, not a consensus about
legitimacy. Our existing eligibility and score-routing gates remain independent;
missing scores remain missing and all approved classifications remain `IN_REVIEW`.

### Ownership, transitions, versions and races

- **jagusgelos:** `update_case` includes optional expected state and fact guards,
  returning success only for one affected row. Turn claiming inserts before
  processing; the schema has a `(customer_id, turn_id)` primary key. These are
  concrete conditional-write/replay patterns, not proof that every caller supplies
  guards or that an authenticated human owns the case. Declared simulated-credit
  indexes are not proof of installed migration or atomic financial effects.
- **DataBank SV:** the claim endpoint authenticates a role, then writes configured
  `demo_agent_email`. `update_handoff` filters only by case ID, returns no write
  result and has no expected-owner/state/version predicate. It rejects in-place
  packet rewriting, but that is not stale-evidence protection. The inspected
  reply/resolve paths do not visibly enforce claimed ownership. This is demo claim
  wiring, not demonstrated named-human, single-winner takeover.
- **jdlr:** dispute computation reads a stored result, scopes candidates by customer
  and owned card products, revalidates selected candidates and persists a result.
  Store conflict/conditional-write implementation was not inspected; read-before-
  compute is not proof of race-safe idempotency. Customer resolution by supplied
  document number is not evidence of our browser-JWT authorization contract.
- **Across the sample:** reason IDs, policy/model versions, a timeline or an immutable
  packet do not establish evidence freshness/version binding, claim authorization,
  cross-process concurrency, financial settlement or completed human adjudication.

**Safe lessons for the approved takeover:** derive operator identity from the verified
principal, keep authorization in the service, condition claims on claimable state
and expected owner, report conflicts rather than silently overwrite, and persist a
truthful claim audit with queue/detail readback. Test competing claims, repeated
requests, non-operator access and preserved customer isolation. These are design
lessons, not implementation evidence for our repository. Do not add model-derived
priority, deadlines or new rules to this stage.

**Deferred:** human verdicts/rationale, reassignment, information-request workflows,
SLA policy, evidence-version adjudication, trained risk/priority signals, and every
financial/protection action. Consent, claim, verdict and execution remain distinct.

### Exact source inventory and evidence limits

Paths below are relative to
`C:\Factored\competencia\<directory>\<directory>\`; the repeated directory name
is intentional. Ranges identify inspected source, not executed coverage.

| Directory | Inspected files and line ranges |
| --- | --- |
| `factored-hackathon-2026-jagusgelos-main` | `app\policy.py` 1–163, 255–433; `app\state_machine.py` 1–185; `app\cases.py` 1–165, 259–355; `app\turns.py` 1–125; `app\db.py` 100–161; `tests\test_policy_not_overridden.py` 1–100. |
| `factored-hackathon-2026-jdlr-main` | `policies.yaml` 1–142, 853–1000; `services\policy-agent\src\evaluator.ts` 1–221; `services\policy-agent\src\handler.ts` full file (227 lines); `services\policy-agent\src\bedrock\guardrail.ts` 30–120; its `guardrail.test.ts` 1–105; `services\transaction-agent\src\compute-dispute.ts` 1–150, 244–375, 407–425. |
| `factored-hackathon-2026-svengineer-main` | `backend\app\policy\rules.py` full file (344 lines); `backend\app\graph\nodes.py` 160–249; `backend\tests\test_policy.py` full file (129 lines). |
| `factored-hackathon-2026-AIDO-main` | `server\policy\rules.ts` full file (79 lines); `server\policy\config.ts` full file (44 lines); `tests\server\policy.test.ts` full file (131 lines). |
| `factored-hackathon-2026-databank_sv-main` | `app\cases\engine.py` 1–180, 311–404; `app\thresholds_loader.py` full file (72 lines); `app\triage_model.py` 116–163; `app\api\routes.py` 164–197, 620–705; `app\ops\store.py` 842–950; `tests\test_routing_pin.py` full file (68 lines). |
| `factored-hackathon-2026-sofia-main` | `agent\src\sofia_agent\decide\node.py` 1–178; `agent\src\sofia_agent\tools\fake_bank.py` opening disclaimer; `services\src\sofia_services\main.py`, `policy\__init__.py` and `routes\__init__.py` full files. Endpoint/source discovery used local text searches, not runtime calls. |

Authored tests pin policy boundaries, additive escalation, guardrail severity,
null/NaN/date handling and routing personas in the files above; **none were run**.
No source/tests were executed, dependencies installed, credentials accessed, network
requests made or code uploaded. Local source inspection does not verify deployed
behavior, complete authorization, runtime evidence freshness or migration invariants.
No competitor code is reproduced; earlier metrics remain historical team claims.
