# ADR 0009: Operator Verdicts Require Recorded Financial Effects

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-10-04 | cristofima  | cristofima  |

---

## Context

Exclusive operator takeover establishes responsibility but does not adjudicate a
claim. The existing customer resolution and provisional-credit wording cannot
establish that money moved or a card was protected. Product records do not
establish debit-card-to-account relationships. Source ingestion must remain
repeatable without erasing later operational financial adjustments.

The project owner explicitly approved assigned-operator adjudication together
with financial effects, amending debit compensation to use a customer's savings
account first and a checking account as fallback. Browser acceptance remains a
separate user-run gate; approval is not implementation or runtime evidence.

## Decision

Only the currently authenticated assigned operator may issue a valid or invalid
final verdict. Require a rationale and expected case and evidence versions.
Persist the decision and its audit atomically, and reject stale or conflicting
requests. Retire customer final-resolution authority. The agent performs intake
and triage only; a stored fraud score never establishes legitimacy.

An invalid verdict closes as `RESOLVED_INVALID`, without compensation. A valid
verdict remains `PENDING_EFFECTS` until required financial effects are actually
recorded, then closes as `RESOLVED_VALID`. Retries execute the same entitlement,
not another verdict or credit. Existing historical resolution records do not
trigger automatic compensation.

Compensate the full original amount in its original currency. Do not convert
currency, add interest or fees, partially compensate or issue provisional credit.
For debit cards, use an owned eligible savings account, falling back to an owned
eligible checking account. This allocation policy is not a card-account
relationship. For credit cards, record an adjustment reducing card debt, not a
deposit into an unrelated account. Missing financial information or an eligible
destination leaves effects pending rather than fabricating completion.

Use a new case/source-linked movement at execution time; preserve the original
transaction and timestamp. Enforce one compensation entitlement per original
transaction across cases and retries. Financial posting, operational balance
adjustment, effect audit and completed-effect state changes are atomic. Keep
runtime adjustments distinguishable from source balances so source ingestion
cannot overwrite them.

Card protection is a separate reasoned, audited operator action retaining prior
state and cause. Verdicts never automatically block or unblock cards. Application
protection must not be presented as external processor enforcement. Reversals,
reassignment, automatic review timeouts and historical financial backfills are
not approved by this decision.

## Alternatives Considered

- Close valid cases on verdict alone: rejected because closure would claim an
  effect that might never execute.
- Require a debit-card/account foreign key: rejected because no verified link
  exists; the owner approved savings/checking allocation instead.
- Deposit credit-card compensation into any owned account: rejected because it
  does not implement the approved debt adjustment.
- Mutate the original charge or source balance alone: rejected because it loses
  provenance and allows ingestion to erase operational effects.
- Let customers or models issue final verdicts: rejected because intake consent
  and risk routing are not adjudication authority.

## Consequences

Case closure becomes explainable through a recorded verdict and actual effects.
Unique entitlements and atomic posting prevent duplicate compensation, while
separate runtime adjustments preserve repeatable ingestion and source history.

This requires coordinated schema, ingestion, financial read projections, API,
operator UI and localized customer-state changes, plus PostgreSQL concurrency
and rollback acceptance. A blocked effect requires an operational retry instead
of falsely successful closure. External payment-processor protection remains
unavailable without an integration.

Selection among multiple eligible accounts is not specified by the owner's
approval. Execution must not choose an arbitrary account silently: expose eligible
destinations and leave ambiguous effects pending until an explicit selection is
provided. Whether that selection must be made by the customer or may be supplied
by the assigned operator remains an operational-policy review item; it must not
be represented as already approved automatic allocation.
