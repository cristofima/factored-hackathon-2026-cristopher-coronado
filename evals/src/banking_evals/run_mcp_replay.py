"""Opt-in model runner; offline imports do not load production SDKs."""
from __future__ import annotations
from typing import Any

async def run_case(*args: Any, **kwargs: Any) -> dict[str, Any]:
    from banking_evals.mcp.runner import run_case as execute
    return await execute(*args, **kwargs)

def main() -> int:
    from banking_evals.mcp.runner import main as execute
    return execute()

if __name__ == "__main__":
    raise SystemExit(main())
