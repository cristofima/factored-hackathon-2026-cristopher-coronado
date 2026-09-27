"""User profile helper for extracting user identity from auth tokens.

Provides user_id and user_email from the authenticated user's token claims.
In production this would extract information from an OpenID Connect token.
Since OIDC is not implemented in this sample, a mock user profile is used.
"""

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock user profile – simulates data that would come from OIDC claims
# ---------------------------------------------------------------------------

_MOCK_USER_PROFILE = {
    "user_id": "bob-user-123",
    "email": "bob.user@contoso.com",
    "name": "Bob User",
    "roles": ["customer"],
}


class UserProfileHelper:
    """Extracts user identity from the current request context.

    In a real deployment, the ``get_user_id`` and ``get_user_email`` methods
    would resolve values from the authenticated user's OIDC ``id_token`` claims
    (e.g. ``sub`` / ``oid`` for user_id, ``email`` / ``preferred_username`` for
    email).  Because authentication is not wired up in this sample we fall back
    to a mock profile.

    Usage::

        helper = UserProfileHelper()
        user_id = helper.get_user_id()
        email   = helper.get_user_email()
    """

    @staticmethod
    def get_user_id() -> str:
        """Return the unique identifier of the currently logged-in user.

        TODO: Replace with actual OIDC claim extraction (``sub`` or ``oid``).
        """
        return _MOCK_USER_PROFILE["user_id"]

    @staticmethod
    def get_user_email() -> str:
        """Return the email of the currently logged-in user.

        TODO: Replace with actual OIDC claim extraction (``email`` or
        ``preferred_username``).
        """
        return _MOCK_USER_PROFILE["email"]
