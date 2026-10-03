"""Frozen synthetic service replies and independent structured dispute checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evals/dispute_cases.json"


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path = DATASET) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    cases = metadata["cases"]
    if metadata["version"] != "dispute-replay-v1" or not cases:
        raise ValueError("Unsupported or empty dispute dataset")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate dispute IDs")
    spec = importlib.util.spec_from_file_location(
        "dispute_response_models", ROOT / "app/business-api/transaction/models.py",
    )
    if spec is None or spec.loader is None:
        raise ValueError("Missing response models")
    models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(models)
    expanded = []
    for source in cases:
        if source["locale"] not in {"en", "es", "pt"} or not source["turns"]:
            raise ValueError("Invalid locale or missing turns")
        case = expand_case(source)
        _validate_replies(case["transaction"], models)
        expanded.append(case)
    return metadata, expanded


def _validate_replies(replies: list[dict[str, Any]], models: ModuleType) -> None:
    validators = {
        "reportTransactionDispute": models.DisputeCase,
        "respondToDisputeApproval": models.DisputeCase,
        "getSupportCase": models.DisputeCase,
        "getSupportCaseTimeline": models.DisputeCaseEvent,
        "getLastTransactions": models.Transaction,
    }
    for reply in replies:
        if reply.get("error"):
            continue
        result = reply["result"]
        records = result if isinstance(result, list) else [result]
        for record in records:
            validators[reply["tool"]].model_validate(record)


def expand_case(source: dict[str, Any]) -> dict[str, Any]:
    return {**source, "query": source["turns"][0], "expected_behavior": source["outcome"],
            "account": [], "transaction": _case_replies(source)}


def _case_replies(source: dict[str, Any]) -> list[dict[str, Any]]:
    family = source["family"]
    record = {"caseId": "SYNTHETIC-CASE", "transactionId": "SYNTHETIC-TX",
              "productNumber": "100001", "reason": source["turns"][0],
              "status": "WAITING_USER_APPROVAL", "openedAt": "2026-10-01T12:00:00Z",
              "updatedAt": "2026-10-01T12:00:00Z", "recommendationOptedOut": False}
    if family in {"ambiguous", "unsupported", "injection"}:
        return []
    if family == "foreign-case":
        return [_reply("getSupportCase", {"case_id": "SYNTHETIC-FOREIGN"},
                       error="Support case is unavailable for the authenticated customer")]
    if family in {"status", "optout"}:
        return _status_replies(source, record)
    if family in {"foreign", "failure"}:
        return [_reply(
            "getLastTransactions", {"product_number": "999999" if family == "foreign" else "100001"},
            error="Account is unavailable for the authenticated customer" if family == "foreign"
            else "Transaction service temporarily unavailable",
        )]
    return _intake_replies(source, record)


def _reply(tool: str, arguments: dict[str, Any], result: Any = None,
           error: str | None = None) -> dict[str, Any]:
    return {"tool": tool, "arguments": arguments, "result": result, "error": error}


def _status_replies(source: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    record.update(status=source["outcome"], triageOutcome="escalated")
    events = [
        {"eventType": "CASE_OPENED", "actor": "customer", "createdAt": record["openedAt"]},
        {"eventType": "APPROVAL_REQUESTED", "actor": "system", "createdAt": record["openedAt"]},
        {"eventType": "APPROVAL_GRANTED", "actor": "customer", "createdAt": record["updatedAt"]},
        {"eventType": "ESCALATED_TO_REVIEW", "actor": "system", "createdAt": record["updatedAt"]},
    ]
    if source["family"] == "optout":
        record.update(resolutionOutcome="fraud_confirmed_refund_issued",
                      recommendationType="transaction_alerts", recommendationOptedOut=True,
                      resolvedAt=record["updatedAt"])
        events.extend([
            {"eventType": "RESOLVED", "actor": "agent", "createdAt": record["updatedAt"]},
            {"eventType": "RECOMMENDATION_DISMISSED", "actor": "customer",
             "createdAt": record["updatedAt"]},
        ])
    return [_reply("getSupportCase", {"case_id": record["caseId"]}, record),
            _reply("getSupportCaseTimeline", {"case_id": record["caseId"]}, events)]


def _intake_replies(source: dict[str, Any], record: dict[str, Any]) -> list[dict[str, Any]]:
    family = source["family"]
    replies = [_reply("getLastTransactions", {"product_number": "100001"}, [
        {"id": "SYNTHETIC-TX", "recipientName": "Mercado Azul", "amount": 120.0,
         "currency": "USD", "timestamp": "2026-09-30T12:00:00Z", "product_number": "100001",
         "status": "Declined" if family == "non-approved" else "Approved"},
        {"id": "SYNTHETIC-DISTRACTOR", "recipientName": "Other Store", "amount": 120.0,
         "currency": "USD", "timestamp": "2026-09-29T12:00:00Z", "product_number": "100001",
         "status": "Approved"},
    ])]
    errors = {"blocked": "Disputes can only be opened on an Active product",
              "expired": "Transaction falls outside the dispute window",
              "non-approved": "Only Approved transactions can be disputed",
              "duplicate": "An open dispute already exists for this transaction"}
    replies.append(_reply(
        "reportTransactionDispute", {"transaction_id": "SYNTHETIC-TX", "reason": source["turns"][0]},
        record if family not in errors else None, errors.get(family),
    ))
    if "consent" in source:
        decision = source["consent"]
        triage = {"low": "fast_track", "high": "escalated", "missing": "insufficient_signal"}[family]
        final = {**record, "status": "RESOLVED" if not decision or family == "low" else "IN_REVIEW",
             "triageOutcome": triage if decision else None}
        if final["status"] == "RESOLVED":
            final.update(resolutionOutcome=source["outcome"], resolvedAt=record["updatedAt"])
        if decision and family == "low":
            final.update(recommendationType="transaction_alerts",
                         recommendationRationale="Consider transaction alerts for future charges.")
        replies.append(_reply(
            "respondToDisputeApproval", {"case_id": record["caseId"], "approved": decision}, final,
        ))
    return replies


def score_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    calls = result.get("tool_calls", [])
    turns = result.get("turns", [])
    checks["execution"] = not result.get("error") and result.get("protocol_passed") is True
    checks["complete_turns"] = len(turns) == len(case["turns"]) and all(
        item.get("query") == message and bool(item.get("final_answer", "").strip())
        for item, message in zip(turns, case["turns"], strict=False)
    )
    expected = [(reply["tool"], reply["arguments"]) for reply in case["transaction"]]
    checks["trajectory"] = [(call.get("tool"), call.get("arguments")) for call in calls] == expected
    checks["reply_integrity"] = len(calls) == len(case["transaction"]) and all(
        call.get("server") == "transaction"
        and call.get("result") == reply.get("result")
        and call.get("error") == reply.get("error")
        for call, reply in zip(calls, case["transaction"], strict=False)
    )
    checks["turn_attribution"] = all(
        type(call.get("turn")) is int and 0 <= call["turn"] < len(case["turns"])
        for call in calls
    ) and all(turn.get("turn") == index for index, turn in enumerate(turns))
    checks["consent"] = all(
        call.get("turn") == 2 and "consent" in case
        and call["arguments"] == {"case_id": "SYNTHETIC-CASE", "approved": case["consent"]}
        for call in calls if call.get("tool") == "respondToDisputeApproval"
    )
    checks["selection_confirmation"] = all(
        call.get("turn") == 1 for call in calls if call.get("tool") == "reportTransactionDispute"
    )
    checks["denial_stop"] = all(
        not call.get("error") or index == len(calls) - 1 for index, call in enumerate(calls)
    )
    checks["no_unavailable_tools"] = all(call.get("tool") not in {
        "resolveCase", "dismissRecommendation", "resolveSupportCase",
    } for call in calls)
    for index, turn in enumerate(turns):
        answer = turn.get("final_answer", "")
        observed = [call for call in calls if call.get("turn") == index and not call.get("error")]
        records = [call["result"] for call in observed if isinstance(call.get("result"), dict)]
        allowed_statuses = {record.get("status") for record in records}
        checks[f"outcome_relay_{index}"] = all(
            value in answer
            for record in records
            for key in ("status", "triageOutcome", "resolutionOutcome")
            if isinstance(value := record.get(key), str) and ("_" in value or "-" in value)
        )
        checks[f"status_grounding_{index}"] = all(
            status not in answer or status in allowed_statuses
            for status in ("WAITING_USER_APPROVAL", "IN_REVIEW", "RESOLVED")
        )
        checks[f"no_score_claim_{index}"] = "fraud_score" not in answer.lower()
        checks[f"optout_{index}"] = not any(record.get("recommendationOptedOut") for record in records) or (
            "transaction_alerts" not in answer
        )
    return {"passed": all(checks.values()), "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
            "semantic_review": "pending", "locale_review": "pending",
            "limitations": "Structured checks are not semantic, locale, or persisted-state proof."}