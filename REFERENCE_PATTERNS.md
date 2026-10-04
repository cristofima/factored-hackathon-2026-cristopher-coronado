# Reference Patterns From Competitor Research

Distilled from [COMPETITOR_RESEARCH.md](COMPETITOR_RESEARCH.md). Each pattern states
what a competitor did, why it matters against the hackathon rubric
(`C:\Factored\docs\Factored AI & Data Hackathon 2026.md`,
`C:\Factored\docs\Datathon_2026_Kickoff.md`), whether we already have an equivalent,
and how expensive it would be to adopt in the time remaining before submission.

The original recommendations are retained below with current acceptance caveats.
The eight-repository expansion is README-only; documented capabilities are not
verified implementations. Prioritize Lane A (truthful, owned, versioned evidence and
an authorized human verdict) before optional Lane B financial/protection effects.
Customer consent, reviewer adjudication and execution verification are distinct.
These recommendations do not override approved architecture or policy. **Current
approval is queue and claim only:** authenticated operator access, single-winner
claim ownership and auditable queue/detail readback. Verdicts, reassignment,
evidence-version adjudication, deadlines/new triage policy and financial/protection
actions are deferred. Existing recommendations below describe future acceptance,
not permission to implement those features now. Current evaluation evidence is
tracked in [the evaluation guide](evals/README.md).

## Source-verified lessons for queue and claim

The [bounded engine review](COMPETITOR_RESEARCH.md#bounded-source-review-dispute-rule-engines)
records exact local sources for jagusgelos, jdlr, svengineer, AIDO, DataBank SV and
sofia. Five implemented policy engines were inspected; sofia implements an agent
eligibility consumer, while the claimed real service engine was not found in its
inspected service tree. Source inspection and authored tests are not executed results.

- **Keep gates distinct.** Eligibility, routing priority, customer confirmation,
  human claim, legitimacy verdict and execution are different decisions. AIDO's
  passing action is `confirm`; jagusgelos's screening AUTO proceeds to further
  evidence; svengineer's graph applies additional overrides after pure policy.
  Their differing fraud-label policies cannot determine our legitimacy rules.
- **Missing signals are explicit.** Jagusgelos escalates missing required evidence;
  DataBank uses REVIEW fallback; svengineer clarifies or escalates depending on the
  gate. Jdlr's negated generic comparisons can match absent fields despite its
  broad comment. Preserve our missing-as-missing routing; do not infer a score.
- **A role/demo assignee is not human ownership.** DataBank's role-authenticated
  claim writes a configured demo email through an unconditional case-ID update.
  Adopt neither that identity shortcut nor silent overwrite: verified operator
  principal, service authorization, expected-state/owner claim and controlled
  conflict/readback are the safe takeover lessons.
- **A state map is not a concurrency invariant.** Jagusgelos has optional guarded
  updates with affected-row checks and customer-scoped turn uniqueness. This
  supports a compare-and-set pattern, not proof of a complete reviewer claim flow.
  Validate competing and repeated claims, unauthorized roles and customer isolation
  in our own implementation before declaring acceptance.
- **Versions need a stated object.** AIDO policy versions and DataBank model/fallback
  versions do not establish a versioned evidence snapshot. Auditable claim events
  are in scope; stale-evidence verdict guards and financial idempotency remain
  separate, deferred contracts.

No competitor thresholds, synthetic clocks, labels, provenance tags or credit/block
outcomes are policy authority. No source finding closes our own runtime gates.

## Existing equivalents and verification gaps

- **Policy decisions stay out of the LLM.** Historical teams and the new AIDO,
  Calvino, DataBank SV and Sentinel READMEs describe deterministic policy boundaries.
  Our ownership checks and score routing are existing controls, not proof of final
  adjudication. A real authorized reviewer must record a verdict, rationale and
  evidence version; customer approval and simulated assignment cannot substitute.
- **A pre-existing fraud signal is routing evidence, not a verdict.** jdlr, Datti
  and svengineer document score reuse. Our synthetic `fraud_score` has that limited
  role; missing scores stay missing and escalate. `is_fraud` remains an offline
  oracle, not an evaluated agent input. Proof of One's rejected trained risk model
  invalidates a blanket claim that no competitor attempted fraud-model training.
- **Structured handoff instead of raw transcript.** jagusgelos, svengineer, Datti, and
  jdlr all version a handoff payload (facts, actions taken, evidence, open questions).
  Our `SupportCaseDetail.tsx` timeline and case event model provide an audit history,
  not proof of an equivalent structured handoff. Explicit verified/customer-reported
  facts, evidence references, open questions, and reviewer delivery need their own
  contract and runtime verification; a labeling pass cannot establish equivalence.

## Priority patterns from the eight new READMEs

Evidence and source-line references are recorded in
[the README-only expansion](COMPETITOR_RESEARCH.md#readme-only-expansion-eight-new-repositories).
These are recommendations, not changes implemented by this documentation pass.

| Priority | Sources | Reusable pattern | Acceptance boundary for our actions plan |
| --- | --- | --- | --- |
| P0 | AIDO; Fabian; DataBank SV | Separate verified facts, customer statements, inferences, missing signals and source references. | Add retrieval timestamps, contradictions and evidence version; never invent device/IP/3DS evidence or infer fraud from geography alone. |
| P0 | Sentinel; Proof of One; Fabian | Structured handoff plus verified delivery/readback. | Require authenticated reviewer scope, rationale, verdict and version, not merely a ticket or human-written reply. |
| P0 | Robinson-Miranda; The Trident | Explicitly disclose unfinished analyst dossier/queue work. | Our Identity exists; reviewer integration still needs queue owner, priority/deadline, information requests, reassignment and overdue handling. |
| P1 | AIDO; Robinson-Miranda; The Trident | Bind confirmation to one exact pending action; AIDO describes a single-use out-of-band nonce. | Customer consent is not reviewer verdict or financial authority; a nonce design is optional, not an approved new authentication path. |
| P1 | Calvino; Proof of One; Sentinel; The Trident | Report denominators, excluded nulls, small samples, frozen baselines and development exposure. | Keep quality, ownership and semantics separate; an intent or conformance score is not dispute-resolution quality. |
| P1 | DataBank SV; Proof of One | Missing-signal escalation, offline-label exclusion and fail-closed dependency failure. | Evaluate owned/foreign/missing cases independently of prompts; fail closed without releasing unsupported banking facts. |
| Deferred | DataBank SV; Robinson-Miranda; The Trident | Confirm then re-read protection/action outcomes. | Lane B still requires explicit policy/migration approval, verified product relationships and atomic/idempotent financial invariants. |

### Implementation and verification gaps, not competitor feature parity

- Preserve the Account/Transaction workflow, PostgreSQL/SQLModel and independent JWT,
  introspection and agent-only identity boundaries. Database object grants in Fabian's
  README are not a replacement for customer ownership checks or reviewer permissions.
- Build strictly pre-event history with approved time windows, canonical types/statuses,
  currency grouping, complete pagination, minimum samples, coverage and freshness.
  Typed evidence does not by itself prevent temporal leakage.
- Guard stale evidence and concurrent reviewer decisions in the Transaction service.
  Neither customer timelines nor Identity administration establishes that invariant.
- Measure preparation effort and reviewer handling time separately from queue/external
  waits and total elapsed time. Calvino's complaint-duration baseline and Sentinel's
  intent score are not evidence of our operational savings.
- If Lane B is separately approved, require DB uniqueness/idempotency, atomic
  posting/balance/state/event changes, linked reversals and ingestion-overwrite
  protection. No newly reviewed README establishes this complete contract.

## Worth adopting, cheap

- **Name the five rubric metrics verbatim in our own evaluation output.** Several
  competitors (CRUDmakers, jagusgelos, sofia) report "safe automated resolution,"
  "containment," "escalation quality," "unsafe outcomes," "cost/latency" using the
  rubric's own vocabulary. This costs nothing beyond labeling discipline in our eval
  report and slide deck, and makes the rubric mapping obvious to a grader skimming
  multiple submissions quickly.
- **Declare sample sizes next to every reported number.** Historical examples
  include jagusgelos (29 scenarios), sofia (30 cases) and jdlr (102/17 cases).
  Calvino additionally reports null exclusions and small samples. Publish task,
  denominator, data exposure, baseline and uncertainty beside each metric; do not
  assume this reporting is universal or that scenario definitions are results.
- **Explicit baseline-vs-proposed framing, even for a small set.** svengineer ran
  their classifier baseline in sprint 1 specifically so they wouldn't be doing it
  under deadline pressure. Lesson: build the simplest possible baseline first (for
  example, "escalate everything," or "the triage prompt alone with no fraud_score
  signal") and lock in its numbers before iterating on the proposed system, so the
  comparison always exists even if the proposed system changes later.
- **State an explicit limitations/honesty section.** jdlr's "honest limitations"
  paragraph (mock data, synthetic eval set, no fine-tuning attempted, human-agent cost
  not modeled) and noema's data-quality pivot (documenting that 83% of their dataset's
  transactions predate the account) both turn an acknowledged gap into rubric-visible
  rigor instead of a hidden risk. We already have good raw material for this
  (the real-clock dispute-window caveat, per-record missing-signal checks,
  `is_fraud`-only-offline framing and simulated outcomes without financial effects);
  it mainly needs to be collected into the submission-facing deck/README
  rather than left scattered across internal planning docs.

## Worth adopting, moderate cost

- **An optional classifier-versus-threshold experiment**, only after evidence,
  reviewer and evaluation acceptance work. Proof of One documents a rejected
  supervised fraud-risk experiment, so this is not a novelty claim. If attempted,
  use strictly pre-event features, independent splits and a usefulness gate; keep
  labels offline and never let a model replace the authorized reviewer. See
  [the evaluation proposal](ADAPTED_EVALUATION_PLAN.md).
- **A fixed held-out conversational evaluation set with the six categories the
  hackathon brief names explicitly** (normal, ambiguous/unsupported, human-required,
  adversarial/injection, multilingual, workflow-progression). This is the single
  largest evaluation gap identified in the previous research pass. The repository
  has 18 fixed definitions/offline baseline and a separate 25-case development-exposed
  dispute replay. Neither is paired real-model acceptance evidence. Preserve separate
  `eval-quality` and `eval-authz` lanes, semantic/locale review, injection resistance,
  consent, reviewer and outcome checks. Definitions alone are not observed results.

## Interesting but not worth adopting before the deadline

- **A trained intent/priority classifier as a second signal on top of policy rules**
  (CRUDmakers's route classifier, Datti's M2 intent classifier, jagusgelos's priority
  classifier, sofia's intent router). All of these are additive refinements to a
  triage step that already works deterministically for us; they improve polish, not
  rubric coverage we're currently missing, and they require their own labeled data,
  train/test split discipline, and leakage checks to do credibly. Lower priority than
  closing the held-out agent-level evaluation gap.
- **A transaction/entity matcher with embedding similarity** (jdlr's 95.1% Recall@1
  matcher). Relevant only if our workflow needed to resolve an ambiguous, unnamed
  transaction from free text; our current flow already has the customer confirm a
  specific transaction (`getLastTransactions` / `getTransactionsByRecipientName`), so
  this solves a problem we do not currently have.
- **Real cloud infrastructure as the orchestration layer** (jdlr's Step
  Functions + per-agent Lambdas). Interesting for production credibility, but
  reproducing it now would trade scarce time for infrastructure polish instead of the
  rubric's explicitly-weighted evaluation evidence. Our existing Terraform App Service
  stack plus local dev stack already demonstrates "a credible route to operation"
  reasonably well without this.
- **A full analyst-console redesign** can remain deferred; the minimum reviewer
  workflow cannot. Datti and Fabian describe consoles, while Robinson-Miranda and
  The Trident explicitly leave their queues unfinished. Existing Identity/operator
  support is not a completed authorized-reviewer experience. The currently approved
  delivery is queue and claim only. The Lane A packet and scoped verdict remain
  deferred acceptance goals, without expanding specialist scope.

## Explicitly rejected by a competitor, useful as a sanity check for us

- noema's historical rejection of disputes as too agentic is a useful scope
  warning, not an acceptance ruling. Evaluating a deterministic score threshold
  against offline labels validates a routing policy; it does not train a model or
  establish agent semantic quality. Proof of One's rejected model is useful negative
  evidence, not a missing feature to copy. Our submission should show measured,
  paired evidence for the actual AI intake/evidence workflow and human handoff,
  without relabeling threshold validation as trained-model evidence.
