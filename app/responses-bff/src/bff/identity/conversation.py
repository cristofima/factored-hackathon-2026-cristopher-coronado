"""Authenticated conversation token ownership."""

import base64
import hashlib
import hmac
import json

from fastapi import HTTPException, status

from bff.config.settings import Settings


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


def _response_token(response_id: str, user_id: str, settings: Settings) -> str:
    encoded = base64.urlsafe_b64encode(response_id.encode()).decode().rstrip("=")
    value = f"v2.{encoded}"
    return f"{value}.{_response_signature(value, user_id, settings)}"


def _response_signature(value: str, user_id: str, settings: Settings) -> str:
    scope = json.dumps(
        [user_id, settings.responses_upstream_mode, settings.responses_agent_endpoint, value],
        separators=(",", ":"),
    )
    return _conversation_signature(scope, "response-continuation", settings)


def _previous_response(token: str, user_id: str, settings: Settings) -> str:
    if len(token) > 2048:
        raise _forbidden_conversation()
    try:
        version, encoded, signature = token.split(".")
        if version != "v2" or not hmac.compare_digest(
            signature, _response_signature(f"{version}.{encoded}", user_id, settings)
        ):
            raise _forbidden_conversation()
        response_id = base64.b64decode(
            encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
        ).decode()
        if not response_id or len(response_id) > 512:
            raise _forbidden_conversation()
        return response_id
    except (ValueError, UnicodeError):
        raise _forbidden_conversation() from None


def _forbidden_conversation() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "ACCESS_DENIED"},
    )
