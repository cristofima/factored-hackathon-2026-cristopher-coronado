"""Paired synthetic dispute replay; baseline is offline, proposed requires explicit model settings."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import platform
import sys
from time import perf_counter
from typing import Any
import unicodedata
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evals.dispute_replay import (
    DATASET, display_value, expanded_fingerprint, fingerprint, load_cases, score_case,
)
from evals.mcp_replay import ReplayReply, ReplayServer
from evals.evidence import (
    CURRENT_RESULT, available_output, controlled_error, customer_identity,
    register_result, sanitize, unique_output,
)


def normalized(message: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKD", message.casefold())
                   if not unicodedata.combining(character))


class DeterministicIntake:
    """Conservative finite-state intake using only customer turns and tool results."""

    def __init__(self, locale: str, session: Any) -> None:
        self.locale = locale
        self.session = session
        self.selected: dict[str, Any] | None = None
        self.case: dict[str, Any] | None = None
        self.preview: dict[str, Any] | None = None
        self.reason = ""
        self.stopped = False

    def text(self, key: str) -> str:
        messages = {
            "clarify": ("Which account, merchant and amount?", "¿Qué cuenta, comercio e importe?",
                        "Qual conta, estabelecimento e valor?"),
            "unsupported": ("That request is unavailable here.", "Esa solicitud no está disponible aquí.",
                            "Essa solicitação não está disponível aqui."),
            "unavailable": ("The requested resource or service is unavailable. No action was confirmed.",
                            "El recurso o servicio no está disponible. No se confirmó ninguna acción.",
                            "O recurso ou serviço está indisponível. Nenhuma ação foi confirmada."),
            "confirm": ("Is this the transaction?", "¿Es esta la transacción?", "Essa é a transação?"),
            "approval": ("Approve or decline investigation of this dispute?",
                         "¿Aprueba o rechaza la investigación de este reclamo?",
                         "Aprova ou recusa a investigação desta disputa?"),
            "proposal": (
                "May I create this dispute case and send it for review? This does not refund, credit or block a card.",
                "¿Autoriza crear este reclamo y enviarlo a revisión? Esto no reembolsa, acredita ni bloquea una tarjeta.",
                "Autoriza criar esta disputa e enviá-la para análise? Isso não reembolsa, credita nem bloqueia um cartão.",
            ),
            "declined": ("No case was created.", "No se creó ningún reclamo.", "Nenhuma disputa foi criada."),
            "recorded": ("Service-reported outcome", "Resultado informado por el servicio",
                         "Resultado informado pelo serviço"),
            "recommendation": ("Optional transaction alerts", "Alertas de transacciones opcionales",
                               "Alertas de transações opcionais"),
        }
        return messages[key][("en", "es", "pt").index(self.locale)]

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        reply = await self.session.call_tool(tool, arguments)
        if reply.isError:
            self.stopped = True
            raise ValueError("Controlled synthetic tool denial or unavailability")
        return json.loads(reply.content[0].text)

    def outcome(self, record: dict[str, Any]) -> str:
        fields = [record.get(key) for key in ("caseId", "status", "triageOutcome", "resolutionOutcome")]
        translated = []
        for value in fields:
            if not value:
                continue
            text = display_value(value, self.locale)
            if value != record.get("caseId") and ("_" in value or "-" in value):
                text += f" ({value})"
            translated.append(text)
        fields = translated
        answer = self.text("recorded") + ": " + ", ".join(str(value) for value in fields if value)
        if record.get("recommendationType") and not record.get("recommendationOptedOut"):
            answer += ". " + self.text("recommendation") + ": " + display_value(
                record["recommendationType"], self.locale,
            )
        return answer

    async def run(self, message: str) -> str:
        if self.stopped:
            return self.text("unavailable")
        text = normalized(message)
        try:
            if self.case is not None:
                return await self.respond(text)
            if self.preview is not None:
                approved = bool(re.search(r"\b(approve|apruebo|aprovo|authorize|autorizo)\b", text))
                declined = bool(re.search(r"\b(no|cancel|decline|rechazo|recuso|nao)\b", text))
                if approved == declined:
                    return self.text("proposal")
                if declined:
                    self.preview = None
                    self.selected = None
                    self.stopped = True
                    return self.text("declined")
                self.case = await self.call("reportTransactionDispute", {
                    "preview_token": self.preview["previewToken"],
                })
                return self.outcome(self.case)
            if self.selected is not None:
                if not re.search(r"\b(yes|si|sim)\b", text) or not re.search(r"transa", text):
                    return self.text("confirm")
                self.preview = await self.call("previewTransactionDispute", {
                    "transaction_id": self.selected["id"], "reason": self.reason,
                })
                transaction = self.preview["transaction"]
                context = " | ".join(str(transaction[key]) for key in (
                    "recipientName", "amount", "currency", "timestamp",
                ))
                location = [transaction.get(key) for key in ("transactionCountry", "transactionCity")]
                context += " | " + ", ".join(value for value in location if value) if any(location) else ""
                return context + ". " + self.preview["reason"] + ". " + self.text("proposal")
            if any(phrase in text for phrase in ("credit limit", "admin mode", "all customers")):
                return self.text("unsupported")
            case_match = re.search(r"\b(?:case|caso)\s+([A-Z0-9]+(?:-[A-Z0-9]+)+)\b", message, re.IGNORECASE)
            if case_match:
                case_id = case_match.group(1).upper()
                record = await self.call("getSupportCase", {"case_id": case_id})
                events = await self.call("getSupportCaseTimeline", {"case_id": case_id})
                self.case = record
                answer = self.outcome(record) + "; " + ", ".join(event["eventType"] for event in events)
                if record["status"] == "WAITING_USER_APPROVAL":
                    answer += ". " + self.text("approval")
                return answer
            account = re.search(r"\b(?:account|cuenta|conta)\s+(\d+)\b", text)
            if not account:
                return self.text("clarify")
            transactions = await self.call("getLastTransactions", {"product_number": account.group(1)})
            amount = re.search(r"\$(\d+(?:\.\d{1,2})?)", text)
            candidates = [transaction for transaction in transactions if amount
                          and transaction.get("amount") == float(amount.group(1))
                          and transaction.get("recipientName")
                          and normalized(transaction.get("recipientName") or "") in text]
            if len(candidates) != 1:
                return self.text("clarify")
            self.selected = candidates[0]
            self.reason = message
            return " | ".join(str(self.selected[key]) for key in ("recipientName", "amount", "timestamp")) \
                + ". " + self.text("confirm")
        except ValueError:
            return self.text("unavailable")

    async def respond(self, message: str) -> str:
        assert self.case is not None
        if self.case["status"] != "WAITING_USER_APPROVAL":
            return self.outcome(self.case)
        approved = bool(re.search(r"\b(approve|apruebo|aprovo)\b", message))
        declined = bool(re.search(r"\b(no|cancel|decline|rechazo|recuso|nao)\b", message))
        if approved == declined:
            return self.text("approval")
        self.case = await self.call("respondToDisputeApproval", {
            "case_id": self.case["caseId"], "approved": approved,
        })
        return self.outcome(self.case)


async def run_baseline(case: dict[str, Any]) -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    servers = {name: ReplayServer(name, [ReplayReply(**reply) for reply in case[name]], trace)
               for name in ("account", "transaction")}
    result: dict[str, Any] = {"case_id": case["id"], "locale": case["locale"], "turns": [],
                              "protocol_passed": False, "tool_calls": trace,
                              "identity_fixture": customer_identity(case["locale"])}
    register_result(result)
    try:
        async with AsyncExitStack() as stack:
            sessions = {name: await stack.enter_async_context(server.connect())
                        for name, server in servers.items()}
            comparator = DeterministicIntake(case["locale"], sessions["transaction"])
            for index, message in enumerate(case["turns"]):
                for server in servers.values():
                    server.turn = index
                started = perf_counter()
                entry = {"turn": index, "query": message, "completed": False, "final_answer": ""}
                result["turns"].append(entry)
                answer = await comparator.run(message)
                entry.update(final_answer=answer, response={"text": answer}, completed=True,
                             latency_seconds=perf_counter() - started)
            for server in servers.values():
                server.assert_complete()
            result["protocol_passed"] = True
    except Exception as error:
        result["error"] = {"type": type(error).__name__, "message": "Synthetic baseline execution failed"}
    result["replay_failures"] = {name: server.failures for name, server in servers.items()}
    result["unconsumed_replies"] = {name: len(server.replies) - server._position
                                    for name, server in servers.items()}
    return result


def rescore(report: dict[str, Any], cases: list[dict[str, Any]], dataset_hash: str) -> bool:
    if report.get("dataset_sha256") != dataset_hash:
        raise ValueError("Dataset hash differs from saved run")

    if report.get("schema_version") != 1 or report.get("system") not in {"baseline", "proposed"}:
        raise ValueError("Unsupported report schema or system")
    if report["system"] == "proposed" and not report.get("model"):
        raise ValueError("Missing model deployment evidence")
    results = report["results"]
    if len(results) != len(cases) or {result["case_id"] for result in results} != {case["id"] for case in cases}:
        raise ValueError("Missing, duplicated, or unexpected cases")
    lookup = {case["id"]: case for case in cases}
    for result in results:
        if result.get("locale") != lookup[result["case_id"]]["locale"]:
            raise ValueError("Saved locale differs from dataset")
        result["score"] = score_case(lookup[result["case_id"]], result)
    if report.get("expanded_inputs_sha256") != expanded_fingerprint(cases):
        raise ValueError("Expanded input hash missing or differs from saved run")
    report["scorer_sha256"] = fingerprint(ROOT / "evals" / "dispute_replay.py")
    return all(result["score"]["passed"] for result in results)


def case_latency(result: dict[str, Any]) -> float | None:
    turns = result.get("turns", [])
    if (result.get("error") or not turns or not result["score"]["passed"]
            or any(turn.get("error") or not turn.get("completed") for turn in turns)
            or not result["score"]["checks"]["complete_turns"]):
        return None
    values = [turn.get("latency_seconds") for turn in turns]
    if any(type(value) not in {int, float} or not math.isfinite(value) or value < 0
           for value in values):
        return None
    return sum(values)


def compare_reports(
    baseline: dict[str, Any], proposed: dict[str, Any],
    cases: list[dict[str, Any]], dataset_hash: str,
) -> dict[str, Any]:
    if baseline.get("system") != "baseline" or proposed.get("system") != "proposed":
        raise ValueError("Comparison requires baseline and proposed reports")
    scorer_hash = fingerprint(ROOT / "evals" / "dispute_replay.py")
    for report in (baseline, proposed):
        if report.get("scorer_sha256") != scorer_hash:
            raise ValueError("Comparison requires the current identical scorer fingerprint")
        if report.get("expanded_inputs_sha256") != expanded_fingerprint(cases):
            raise ValueError("Comparison requires identical frozen expanded inputs")
    rescore(baseline, cases, dataset_hash)
    rescore(proposed, cases, dataset_hash)
    baseline_results = {result["case_id"]: result for result in baseline["results"]}
    proposed_results = {result["case_id"]: result for result in proposed["results"]}
    pairs = []
    for case in cases:
        first, second = baseline_results[case["id"]], proposed_results[case["id"]]
        pairs.append({
            "case_id": case["id"], "locale": case["locale"],
            "baseline_passed": first["score"]["passed"], "proposed_passed": second["score"]["passed"],
            "structured_delta": int(second["score"]["passed"]) - int(first["score"]["passed"]),
            "baseline_seconds": case_latency(first),
            "proposed_seconds": case_latency(second),
        })
    return {"dataset_sha256": dataset_hash, "cases": pairs, "offline_or_simulated": True,
            "improvements": sum(pair["structured_delta"] > 0 for pair in pairs),
            "regressions": sum(pair["structured_delta"] < 0 for pair in pairs),
            "wins": sum(pair["structured_delta"] > 0 for pair in pairs),
            "losses": sum(pair["structured_delta"] < 0 for pair in pairs),
            "ties": sum(pair["structured_delta"] == 0 for pair in pairs),
            "baseline_failures": sum(not pair["baseline_passed"] for pair in pairs),
            "proposed_failures": sum(not pair["proposed_passed"] for pair in pairs),
            "semantic_review": "pending", "locale_review": "pending",
            "cost": "unavailable; no prices supplied",
            "limitation": "Paired structured checks, not semantic or persisted resolution evidence."}


def write_artifacts(report: dict[str, Any], output: Path) -> bool:
    report = sanitize(report)
    output = available_output(output)
    print(f"Saving redacted replay evidence to {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    results = report["results"]
    failures = sum(not result["score"]["passed"] for result in results)
    suite = ElementTree.Element("testsuite", name="dispute-structured-replay", tests=str(len(results)),
                                 failures=str(failures))
    for result in results:
        test = ElementTree.SubElement(suite, "testcase", name=result["case_id"],
                                       classname="dispute." + report["system"])
        if not result["score"]["passed"]:
            ElementTree.SubElement(test, "failure", message="Structured dispute check failed").text = ", ".join(
                result["score"]["failed_checks"])
    ElementTree.ElementTree(suite).write(output.with_suffix(".xml"), encoding="utf-8", xml_declaration=True)
    lines = ["## Dispute Replay", "", f"System: {report['system']}. Cases: {len(results)}. Failures: {failures}.",
             "", "Synthetic MCP replies; structured checks only. Semantic and locale review pending.",
             "No persisted-state, service authorization, unseen quality or production improvement claim.",
             "", "| Language | Cases | Structured Passes |", "| --- | --- | --- |"]
    for locale in ("en", "es", "pt"):
        group = [result for result in results if result["locale"] == locale]
        lines.append(f"| {locale} | {len(group)} | {sum(result['score']['passed'] for result in group)} |")
    latencies = sorted(value for result in results
                       if (value := case_latency(result)) is not None)
    lines.extend(["", f"Complete case timing: {len(latencies)}/{len(results)}. "
                  "Missing or incomplete timing is excluded, not recorded as zero."])
    if latencies:
        lines.extend(["", f"Case latency p50: {latencies[(len(latencies)-1)//2]:.4f}s; "
                      f"p95: {latencies[min(len(latencies)-1, int(len(latencies)*0.95))]:.4f}s."])
    lines.extend(["", "Priced cost: unavailable (no pricing assumptions supplied).",
                  "Safe resolution and cost per successful resolution: not established by structured replay."])
    if "comparison" in report:
        comparison = report["comparison"]
        lines.extend(["", f"Paired structured wins: {comparison['wins']}; "
                      f"ties: {comparison['ties']}; losses: {comparison['losses']}.",
                      f"Baseline failures: {comparison['baseline_failures']}; "
                      f"proposed failures: {comparison['proposed_failures']}.",
                      "Semantic review remains pending; ties can include failures in both systems."])
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bool(results) and failures == 0


async def main_async(args: argparse.Namespace) -> int:
    metadata, cases = load_cases(args.dataset)
    dataset_hash = fingerprint(args.dataset)
    if args.rescore:
        report = json.loads(args.rescore.read_text(encoding="utf-8"))
    else:
        if args.system == "baseline":
            results = [await execute_case(run_baseline, case, args.timeout_seconds) for case in cases]
        else:
            if not args.project_endpoint or not args.model:
                raise ValueError("Proposed replay requires explicit endpoint and model")
            from evals.run_mcp_replay import run_case
            from agent_framework.foundry import FoundryChatClient
            from azure.identity.aio import AzureCliCredential
            async with AzureCliCredential() as credential:
                client = FoundryChatClient(project_endpoint=args.project_endpoint, model=args.model,
                                           credential=credential)
                async def proposed(case: dict[str, Any]) -> dict[str, Any]:
                    return await run_case(client, case, args.timeout_seconds)

                results = [await execute_case(proposed, case, args.timeout_seconds) for case in cases]
        report = {
            "schema_version": 1, "dataset_version": metadata["version"],
            "dataset_sha256": dataset_hash, "split": metadata["split"], "system": args.system,
            "results": results, "created_at": datetime.now(timezone.utc).isoformat(),
            "model": args.model, "model_execution": "real" if args.system == "proposed" else "none",
            "offline_or_simulated": True, "foundry_submission": "not_submitted",
            "prompt_sha256": fingerprint(ROOT / "app/agent/app/agents/azure_chat/transaction_agent.py"),
            "baseline_sha256": fingerprint(Path(__file__)), "semantic_review": "pending",
            "python_version": platform.python_version(),
            "scorer_sha256": fingerprint(ROOT / "evals/dispute_replay.py"),
            "contract_sha256": {
                name: fingerprint(ROOT / "app/business-api" / name / "mcp_tools.py")
                for name in ("account", "transaction")
            },
            "timeout_seconds": args.timeout_seconds,
            "expanded_inputs_sha256": expanded_fingerprint(cases),
            "operator_adjudication": "blocked: contract not approved",
            "identity_acceptance": "not established: synthetic internal envelope, no JWT introspection",
        }
    report = sanitize(report)
    passed = rescore(report, cases, dataset_hash)
    if args.compare_baseline:
        baseline = sanitize(json.loads(args.compare_baseline.read_text(encoding="utf-8")))
        report["comparison"] = compare_reports(baseline, report, cases, dataset_hash)
    output = args.output or unique_output(ROOT / "evals" / "results", f"dispute-{report['system']}")
    return 0 if write_artifacts(report, output) and passed else 1


async def execute_case(runner: Any, case: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    token = CURRENT_RESULT.set(None)
    try:
        async with asyncio.timeout(timeout_seconds):
            return await runner(case)
    except Exception as error:
        result = CURRENT_RESULT.get() or {"case_id": case["id"], "locale": case["locale"],
                                          "turns": [], "tool_calls": []}
        result.update(protocol_passed=False, error=controlled_error(error))
        return sanitize(result)
    finally:
        CURRENT_RESULT.reset(token)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("baseline", "proposed"), default="baseline")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rescore", type=Path)
    parser.add_argument("--compare-baseline", type=Path)
    parser.add_argument("--project-endpoint")
    parser.add_argument("--model")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("Timeout must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())