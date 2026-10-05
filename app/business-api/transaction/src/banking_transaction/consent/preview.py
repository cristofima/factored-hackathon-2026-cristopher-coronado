"""Short-lived signed consent proposals; no pre-consent persistence."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import jwt
from banking_shared.models import Product, TransactionRecord

PREVIEW_LIFETIME = timedelta(minutes=10)
RECOVERY_LIFETIME = timedelta(hours=24)
PREVIEW_AUDIENCE = "transaction-dispute-preview"


class DisputePreviewError(ValueError):
    """A proposal is invalid, expired, or no longer matches its evidence."""

    def __init__(self, code: str = "DISPUTE_PREVIEW_INVALID") -> None:
        self.code = code
        super().__init__(code)


def evidence_digest(transaction: TransactionRecord, product: Product) -> str:
    evidence = {
        "transaction": transaction.model_dump(mode="json"),
        "product": {
            key: getattr(product, key)
            for key in ("product_id", "customer_id", "product_type", "product_number",
                        "currency", "product_status")
        },
    }
    serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


def issue_preview(
    secret: str, customer_id: str, transaction_id: str, reason: str, evidence: str,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    expires = now + PREVIEW_LIFETIME
    token = jwt.encode({
        "aud": PREVIEW_AUDIENCE, "sub": customer_id, "transactionId": transaction_id,
        "reason": reason, "evidence": evidence, "jti": uuid4().hex[:20].upper(),
        "iat": int(now.timestamp()), "acceptUntil": int(expires.timestamp()),
        "exp": int((now + RECOVERY_LIFETIME).timestamp()),
    }, secret, algorithm="HS256")
    return token, expires


def read_preview(secret: str, token: str, customer_id: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], audience=PREVIEW_AUDIENCE,
            options={"require": ["sub", "iat", "exp", "jti", "transactionId",
                                 "reason", "evidence", "acceptUntil"]},
        )
    except (jwt.InvalidTokenError, TypeError, ValueError, OverflowError) as error:
        raise DisputePreviewError() from error
    if any(not isinstance(claims[key], str) or not claims[key].strip()
           for key in ("sub", "jti", "transactionId", "reason", "evidence")):
        raise DisputePreviewError()
    if (len(claims["jti"]) != 20 or any(c not in "0123456789ABCDEF" for c in claims["jti"])
            or any(type(claims[key]) is not int for key in ("iat", "exp", "acceptUntil"))
            or not claims["iat"] < claims["acceptUntil"] < claims["exp"]):
        raise DisputePreviewError()
    if claims["sub"] != customer_id:
        raise PermissionError("Dispute preview unavailable")
    return claims


def configured_preview_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required for dispute previews")
    return secret
