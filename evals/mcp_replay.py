"""Synthetic, in-memory MCP transport for isolated workflow evaluations."""

from __future__ import annotations

import ast
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from mcp import ClientSession, types
from mcp.server import Server
from mcp.shared.memory import create_connected_server_and_client_session


ROOT = Path(__file__).resolve().parents[1]


def _argument_schema(argument: ast.arg) -> dict[str, str]:
    annotation = argument.annotation
    description = None
    if isinstance(annotation, ast.Subscript):
        if not isinstance(annotation.value, ast.Name) or annotation.value.id != "Annotated":
            raise ValueError("Unsupported contract annotation")
        if not isinstance(annotation.slice, ast.Tuple) or len(annotation.slice.elts) != 2:
            raise ValueError("Unsupported Annotated contract")
        annotation, description_node = annotation.slice.elts
        description = ast.literal_eval(description_node)
    if not isinstance(annotation, ast.Name) or annotation.id not in {"str", "bool"}:
        raise ValueError("Unsupported contract annotation")
    schema = {
        "type": "string" if annotation.id == "str" else "boolean",
    }
    if description is not None:
        schema["description"] = description
    return schema


def _tool_contract(function: ast.FunctionDef | ast.AsyncFunctionDef, decorator: ast.Call) -> types.Tool:
    metadata = {item.arg: ast.literal_eval(item.value) for item in decorator.keywords}
    properties = {
        argument.arg: _argument_schema(argument)
        for argument in function.args.args if argument.arg != "headers"
    }
    schema: dict[str, Any] = {
        "type": "object", "properties": properties, "additionalProperties": False,
    }
    if properties:
        schema["required"] = list(properties)
    return types.Tool(
        name=metadata["name"], description=metadata["description"], inputSchema=schema,
    )


def load_contracts(server: str) -> list[types.Tool]:
    """Read public tool declarations without importing database-backed services."""
    if server not in {"account", "transaction"}:
        raise ValueError("Unknown replay server")
    source = ROOT / "app" / "business-api" / server / "mcp_tools.py"
    contracts = []
    for function in ast.parse(source.read_text(encoding="utf-8")).body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in function.decorator_list:
            if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and isinstance(decorator.func.value, ast.Name)
                    and decorator.func.value.id == "mcp" and decorator.func.attr == "tool"):
                contracts.append(_tool_contract(function, decorator))
    return contracts


@dataclass(frozen=True)
class ReplayReply:
    tool: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None


@dataclass
class ReplayServer:
    name: str
    replies: list[ReplayReply]
    trace: list[dict[str, Any]] | None = None
    turn: int | None = None
    calls: list[dict[str, Any]] = field(default_factory=list, init=False)
    failures: list[str] = field(default_factory=list, init=False)
    _position: int = field(default=0, init=False)

    def build(self) -> Server:
        server = Server(f"banking-replay-{self.name}")
        contracts = load_contracts(self.name)

        @server.list_tools()
        async def list_tools() -> list[types.Tool]:
            return contracts

        @server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
            call = {"server": self.name, "tool": name, "arguments": arguments}
            if self.turn is not None:
                call["turn"] = self.turn
            self.calls.append(call)
            if self.trace is not None:
                call["sequence"] = len(self.trace)
                self.trace.append(call)
            if self._position >= len(self.replies):
                error = f"Unexpected replay call: {self.name}/{name}"
            else:
                reply = self.replies[self._position]
                if name != reply.tool or arguments != reply.arguments:
                    error = f"Replay call does not match step {self._position}: {self.name}/{name}"
                else:
                    self._position += 1
                    call.update(result=reply.result, error=reply.error)
                    return types.CallToolResult(
                        content=[types.TextContent(type="text", text=(
                            reply.error if reply.error else json.dumps(reply.result, ensure_ascii=False)
                        ))],
                        isError=reply.error is not None,
                    )
            self.failures.append(error)
            call["error"] = error
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=error)], isError=True,
            )

        return server

    def assert_complete(self) -> None:
        if self.failures or self._position != len(self.replies):
            raise AssertionError(
                f"{self.name}: consumed {self._position}/{len(self.replies)} replies; "
                f"failures={self.failures}"
            )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[ClientSession]:
        async with create_connected_server_and_client_session(self.build()) as session:
            yield session