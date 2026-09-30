"""Resolve user profile fields from the verified BFF request identity."""

from app.common.internal_identity import get_internal_principal


class UserProfileHelper:
    """Read request-scoped identity without sample-profile fallbacks."""

    @staticmethod
    def get_user_id(secret: str) -> str:
        """Return the verified subject of the current request."""
        return get_internal_principal(secret).sub

    @staticmethod
    def get_user_email(secret: str) -> str:
        """Return the verified email, rejecting identities without a profile."""
        email = get_internal_principal(secret).email
        if email is None:
            raise ValueError("Authenticated request email is required")
        return email
