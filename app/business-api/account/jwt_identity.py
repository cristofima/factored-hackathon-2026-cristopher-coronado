"""Application JWT verification for browser-facing REST routes."""

from __future__ import annotations

import os
from typing import Annotated

import jwt
from fastapi import Header, HTTPException, status
from jwt import InvalidTokenError

REQUIRED_CLAIMS = ["exp", "sub", "customer_id", "email", "locale"]


def get_jwt_customer_id(authorization: Annotated[str | None, Header()] = None) -> str:
    """Validate the browser's application JWT and return its verified customer_id."""
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT verification is not configured",
        )

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated customer identity is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=os.environ.get("JWT_AUDIENCE", "home-banking-web"),
            issuer=os.environ.get("JWT_ISSUER", "home-banking-api"),
            options={"require": REQUIRED_CLAIMS},
        )
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired identity token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    customer_id = claims.get("customer_id")
    if not isinstance(customer_id, str) or not customer_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired identity token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return customer_id
