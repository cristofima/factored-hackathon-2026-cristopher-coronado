"""Expose known ownership denials without exposing arbitrary MCP exceptions."""

from collections.abc import Awaitable, Callable

from agent_framework import FunctionInvocationContext, FunctionMiddleware
from agent_framework.exceptions import ToolExecutionException


class OwnershipErrorMiddleware(FunctionMiddleware):
    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            await call_next()
        except ToolExecutionException as exception:
            denial = "Account does not belong to the authenticated customer"
            if not str(exception).endswith(denial):
                raise
            context.result = (
                "Error: ACCESS_DENIED. The requested account is unavailable to the "
                "authenticated customer. Stop this lookup; do not query other accounts."
            )