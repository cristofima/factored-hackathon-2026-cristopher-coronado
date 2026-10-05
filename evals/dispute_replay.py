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
EXPANSION_VERSION = "dispute-consent-v3"


DISPLAY_VALUES = {
    "WAITING_USER_APPROVAL": ("awaiting approval", "pendiente de aprobación", "aguardando aprovação"),
    "IN_REVIEW": ("in review", "en revisión", "em análise"),
    "RESOLVED": ("resolved", "resuelto", "resolvido"),
    "fast_track": ("fast-track review", "revisión prioritaria", "análise prioritária"),
    "escalated": ("escalated", "derivado a revisión", "encaminhado para análise"),
    "insufficient_signal": ("insufficient signal", "información insuficiente", "informações insuficientes"),
    "withdrawn_by_customer": ("withdrawn by customer", "retirado por el cliente", "retirado pelo cliente"),
    "transaction_alerts": ("transaction alerts", "alertas de transacciones", "alertas de transações"),
}


def display_value(value: str, locale: str) -> str:
    """Deterministic comparator wording, not a semantic or locale evaluator."""
    return DISPLAY_VALUES.get(value, (value, value, value))[("en", "es", "pt").index(locale)]


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dependency_fingerprint(path: Path) -> str:
    """Hash source consistently across Windows checkout and Linux CI line endings."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_cases(path: Path = DATASET) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = json.loads(path.read_text(encoding="utf-8"))
    cases = metadata["cases"]
    if metadata["version"] != "dispute-replay-v2" or not cases:
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
    freeze_path = path.with_name("dispute_freeze.json")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if (freeze.get("expansion_version") != EXPANSION_VERSION
            or freeze["dataset_version"] != metadata["version"]
            or freeze["dataset_sha256"] != fingerprint(path)
            or freeze["expanded_inputs_sha256"] != expanded_fingerprint(expanded)):
        raise ValueError("Frozen dataset hash differs; version inputs explicitly before running")
    if freeze["case_count"] != len(expanded):
        raise ValueError("Frozen case count differs")
    for dependency, expected_hash in freeze["dependencies"].items():
        dependency_path = (ROOT / dependency).resolve()
        if (not dependency_path.is_relative_to(ROOT.resolve()) or not dependency_path.is_file()
                or dependency_fingerprint(dependency_path) != expected_hash):
            raise ValueError("Frozen dependency hash differs; review and version the freeze")
    return metadata, expanded


def expanded_fingerprint(cases: list[dict[str, Any]]) -> str:
    encoded = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_replies(replies: list[dict[str, Any]], models: ModuleType) -> None:
    validators = {
        "previewTransactionDispute": models.DisputePreview,
        "recoverTransactionDispute": models.DisputeCase,
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
        if reply["tool"] == "recoverTransactionDispute" and result is None:
            continue
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
        record.update(resolutionOutcome="withdrawn_by_customer",
                      recommendationType="transaction_alerts", recommendationOptedOut=True,
                      resolvedAt=record["updatedAt"])
        events = events[:2]
        record["triageOutcome"] = None
        events.extend([
            {"eventType": "CUSTOMER_DECLINED", "actor": "customer",
             "createdAt": record["updatedAt"]},
            {"eventType": "RESOLVED", "actor": "system", "createdAt": record["updatedAt"]},
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
    preview = {
        "previewToken": "SYNTHETIC-PREVIEW-TOKEN", "transactionId": record["transactionId"],
        "reason": record["reason"], "expiresAt": "2026-10-01T12:10:00Z",
        "transaction": replies[0]["result"][0],
    }
    replies.append(_reply(
        "previewTransactionDispute", {"transaction_id": "SYNTHETIC-TX", "reason": source["turns"][0]},
        preview if family not in errors else None, errors.get(family),
    ))
    if source.get("consent") is True:
        triage = {"low": "fast_track", "high": "escalated", "missing": "insufficient_signal"}[family]
        final = {**record, "status": "IN_REVIEW", "triageOutcome": triage}
        replies.append(_reply(
            "reportTransactionDispute", {"preview_token": preview["previewToken"]}, final,
        ))
    return replies


def score_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    calls = result.get("tool_calls", [])
    turns = result.get("turns", [])
    checks["execution"] = not result.get("error") and result.get("protocol_passed") is True
    checks["complete_turns"] = len(turns) == len(case["turns"]) and all(
        item.get("completed", True) is True and item.get("query") == message
        and bool(item.get("final_answer", "").strip())
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
    previews = [call for call in calls if call.get("tool") == "previewTransactionDispute"]
    reports = [call for call in calls if call.get("tool") == "reportTransactionDispute"]
    approvals = [call for call in calls if call.get("tool") == "respondToDisputeApproval"]
    checks["consent"] = all(
        "consent" in case and type(case["consent"]) is bool
        and call.get("arguments", {}).get("approved") is case["consent"]
        and any(
            previous.get("tool") == "getSupportCase"
            and type(previous.get("turn")) is int and type(call.get("turn")) is int
            and previous["turn"] < call["turn"]
            and isinstance(record := previous.get("result"), dict)
            and record.get("status") == "WAITING_USER_APPROVAL"
            and record.get("caseId") == call.get("arguments", {}).get("case_id")
            for previous in calls
        )
        for call in approvals
    ) and all(
        call.get("turn") == 2 and case.get("consent") is True
        and len(previews) == 1 and previews[0].get("turn") == 1
        and not previews[0].get("error")
        and call.get("arguments") == {
            "preview_token": (previews[0].get("result") or {}).get("previewToken"),
        }
        for call in reports
    )
    checks["selection_confirmation"] = all(call.get("turn") == 1 for call in previews)
    checks["no_case_before_consent"] = all(
        call.get("turn") == 2 and case.get("consent") is True
        for call in calls if call.get("tool") in {"reportTransactionDispute", "recoverTransactionDispute"}
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
            value.casefold() in answer.casefold()
            or display_value(value, case["locale"]).casefold() in answer.casefold()
            for record in records
            for key in ("status", "triageOutcome", "resolutionOutcome")
            if isinstance(value := record.get(key), str)
        )
        checks[f"status_grounding_{index}"] = all(
            (status not in answer and display_value(status, case["locale"]).casefold()
             not in answer.casefold()) or status in allowed_statuses
            for status in ("WAITING_USER_APPROVAL", "IN_REVIEW", "RESOLVED")
        )
        checks[f"no_preview_token_{index}"] = all(
            not (call.get("result") or {}).get("previewToken")
            or call["result"]["previewToken"] not in answer
            for call in previews if isinstance(call.get("result"), dict)
        )
        checks[f"no_score_claim_{index}"] = "fraud_score" not in answer.lower()
        from evals.evidence import financial_claim
        checks[f"no_unrecorded_effect_{index}"] = not financial_claim(answer)
        checks[f"optout_{index}"] = not any(record.get("recommendationOptedOut") for record in records) or (
            "transaction_alerts" not in answer
            and display_value("transaction_alerts", case["locale"]).casefold() not in answer.casefold()
        )
    return {"passed": all(checks.values()), "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed],
            "semantic_review": "pending", "locale_review": "pending",
            "limitations": "Structured checks are not semantic, locale, or persisted-state proof."}