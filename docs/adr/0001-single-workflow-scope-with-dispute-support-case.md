# ADR 0001: Single workflow scope — Account/Transaction inquiries with one transaction-dispute support case layer

| Status   | Date       | Proposed by | Approved by |
| -------- | ---------- | ----------- | ----------- |
| Accepted | 2026-10-01 | cristofima  | cristofima  |

---

## Context

The hackathon brief allows choosing one of four example workflows (account/payment
inquiries, card-service support, transaction-dispute intake, or credit-product
eligibility) and is explicit that "implementing more workflows does not earn an
automatic bonus." The forked sample repository
(`Azure-Samples/agent-openai-python-banking-assistant`) already implemented three
cooperating specialist agents — Account, Transaction, and Payment — under one
handoff orchestrator. A single ten-day developer had to decide how much of that
surface to keep, and whether a support-case/HITL layer (required by the rubric's
"involve human agents when needed" and "controlled automation" dimensions) should be
a new conversational specialist or something simpler layered on what already
existed.

## Decision

Keep exactly one active conversational workflow: Account and Transaction specialist
agents under a single `HandoffBuilder` (Microsoft Agent Framework, served through
Foundry Responses). Drop Payment from the active workflow entirely (kept only as
inert infrastructure/compatibility artifacts). Add one persisted support-case
tracking layer, transaction disputes, as a state-machine and set of REST/MCP
endpoints over the existing Account/Transaction tools, not as a new specialist agent
or a fourth `HandoffBuilder` participant.

## Consequences

Easier: one workflow to harden, test, and evaluate instead of three, with the
dispute case reusing the same customer-ownership authorization already built for
Account/Transaction rather than duplicating it for a new agent. Harder: Payment's
invoice-OCR capability becomes unused sunk infrastructure that still has to be
explained in the submission as deliberately disconnected, not abandoned mid-build;
a later pivot to a different track (for example, card-service support) would need
new MCP tools and authorization logic from scratch, since Account/Transaction's
tools don't cover card lifecycle actions.

## Related

- [0002](0002-deterministic-fraud-score-triage-over-trained-model.md) defines how
  the dispute support-case layer this ADR introduces actually triages cases.
