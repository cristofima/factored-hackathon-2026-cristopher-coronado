"""User profile context provider for agent framework.

Provides logged user details and current timestamp to agents via the
Agent Framework context provider mechanism. Delegates user identity
resolution to ``UserProfileHelper``.
"""

from datetime import datetime
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext

from app.common.internal_identity import get_internal_principal

import logging

logger = logging.getLogger(__name__)


class UserProfileProvider(ContextProvider):
    """Injects the current user's email and timestamp into every agent run.

    User identity is resolved from the verified, signed BFF request envelope.
    """

    DEFAULT_SOURCE_ID = "user_profile_provider"

    def __init__(
        self, internal_identity_secret: str, source_id: str = DEFAULT_SOURCE_ID
    ) -> None:
        super().__init__(source_id)
        self._internal_identity_secret = internal_identity_secret

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_current_timestamp() -> str:
        """Return the current date-time formatted as a string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # Context provider hooks
    # ------------------------------------------------------------------

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Provide user profile context before each agent call."""
        principal = get_internal_principal(self._internal_identity_secret)
        user_email = principal.email
        if user_email is None:
            raise ValueError("Authenticated request email is required")
        current_timestamp = self._get_current_timestamp()

        logger.debug(
            "UserProfileProvider injecting context – user=%s, timestamp=%s",
            user_email,
            current_timestamp,
        )

        context.extend_instructions(
            self.source_id,
            "#Logged user information",
        )
        context.extend_instructions(
            self.source_id,
            f"Email: {user_email}",
        )
        context.extend_instructions(
            self.source_id,
            f"Current timestamp: {current_timestamp}",
        )
        language = {"es": "Spanish", "pt": "Portuguese", "en": "English"}[principal.locale]
        context.extend_instructions(
            self.source_id,
            f"Respond to the user in {language} ({principal.locale}), including errors and "
            "unavailable-operation explanations. Use this authenticated profile language "
            "regardless of the language of the user's messages or conversation history. "
            "Keep tool calls and operational data unchanged.",
        )
