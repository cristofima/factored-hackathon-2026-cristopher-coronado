"""Signed identity envelope for trusted internal service calls."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

from bff.identity.models import AuthenticatedUser


def create_internal_identity(user: AuthenticatedUser, secret: str) -> str:
    """Create a stable, signed identity without forwarding the browser JWT."""
    payload = json.dumps(
        {
            "customer_id": user.customer_id,
            "sub": user.sub,
            "email": user.email,
            "locale": user.locale,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), encoded_payload.encode(), hashlib.sha256).hexdigest()
    return f"v1.{encoded_payload}.{signature}"