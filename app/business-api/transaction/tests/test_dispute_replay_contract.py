"""Independent local FastMCP discovery, without database or identity access."""

from __future__ import annotations

import ast
from pathlib import Path
import sys
from unittest.mock import MagicMock

from fastmcp import Client, FastMCP
from fastmcp.server.dependencies import CurrentHeaders
import pytest

from models import DisputeCase, DisputeCaseEvent

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from evals.mcp_replay import load_contracts


@pytest.mark.asyncio
async def test_replay_schemas_match_independent_fastmcp_discovery() -> None:
    for name in ("account", "transaction"):
        source = ROOT / "app/business-api" / name / "mcp_tools.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
        server = FastMCP("isolated-contract-discovery")
        namespace = {
            "mcp": server, "CurrentHeaders": CurrentHeaders,
            "service": MagicMock(), "dispute_service": MagicMock(),
            "Annotated": __import__("typing").Annotated,
        }
        exec(compile(tree, str(source), "exec"), namespace)
        async with Client(server) as client:
            discovered = {tool.name: tool for tool in await client.list_tools()}
        contracts = {tool.name: tool for tool in load_contracts(name)}
        assert contracts.keys() == discovered.keys()
        for tool_name, contract in contracts.items():
            actual = discovered[tool_name]
            assert contract.description == actual.description
            assert contract.inputSchema == actual.inputSchema
    assert "resolveCase" not in contracts
    assert "dismissRecommendation" not in contracts


def test_dispute_response_models_reject_incomplete_fixture_outputs() -> None:
    with pytest.raises(ValueError):
        DisputeCase.model_validate({"caseId": "SYNTHETIC-CASE", "status": "RESOLVED"})
    with pytest.raises(ValueError):
        DisputeCaseEvent.model_validate({"eventType": "RESOLVED"})