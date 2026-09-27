"""User profile context provider for agent framework.

Provides logged user details and current timestamp to agents via the
Agent Framework context provider mechanism. Delegates user identity
resolution to ``UserProfileHelper``.
"""

from datetime import datetime
from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext

from app.helpers.user_profile_helper import UserProfileHelper

import logging

logger = logging.getLogger(__name__)


class UserProfileProvider(ContextProvider):
    """Injects the current user's email and timestamp into every agent run.

    User identity is resolved via ``UserProfileHelper`` which in production
    would extract claims from an OIDC token.
    """

    DEFAULT_SOURCE_ID = "user_profile_provider"

    def __init__(self, source_id: str = DEFAULT_SOURCE_ID, **kwargs: Any):
        super().__init__(source_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_logged_user_email() -> str:
        """Return the email of the currently logged-in user."""
        return UserProfileHelper.get_user_email()

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
        user_email = self._get_logged_user_email()
        current_timestamp = self._get_current_timestamp()

        logger.debug(
            "UserProfileProvider injecting context – user=%s, timestamp=%s",
            user_email,
            current_timestamp,
        )

        context.extend_instructions(
            self.source_id,
            f"#Logged user information",
        )
        context.extend_instructions(
            self.source_id,
            f"Email: {user_email}",
        )
        context.extend_instructions(
            self.source_id,
            f"Current timestamp: {current_timestamp}",
        )
