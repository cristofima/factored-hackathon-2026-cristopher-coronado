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


from banking_evals.resources import repository_root

ROOT = repository_root()


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
    source = ROOT / "app" / "business-api" / server / "src" / f"banking_{server}" / "mcp_tools.py"
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
