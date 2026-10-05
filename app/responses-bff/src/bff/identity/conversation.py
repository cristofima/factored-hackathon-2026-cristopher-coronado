"""Authenticated conversation token ownership."""

import hashlib
import hmac
import secrets
from fastapi import HTTPException, status
from bff.config.settings import Settings

def _conversation_token(user_id: str, settings: Settings) -> str:
    conversation_id = secrets.token_urlsafe(24)
    signature = _conversation_signature(user_id, conversation_id, settings)
    return f"{conversation_id}_{signature}"


def _validate_conversation(token: str, user_id: str, settings: Settings) -> None:
    try:
        conversation_id, signature = token.rsplit("_", maxsplit=1)
    except ValueError:
        raise _forbidden_conversation() from None

    expected = _conversation_signature(user_id, conversation_id, settings)
    if not hmac.compare_digest(signature, expected):
        raise _forbidden_conversation()


def _conversation_signature(user_id: str, conversation_id: str, settings: Settings) -> str:
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
        )
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"{user_id}:{conversation_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _forbidden_conversation() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "ACCESS_DENIED"},
    )
