"""Supabase JWT validation.

Supports both the legacy HS256 JWT secret and modern asymmetric (RS256/ES256) keys
served via JWKS. We prefer JWKS because it doesn't require distributing a shared
secret to every service, but HS256 still works for projects that haven't rotated.

The public entry point is `require_user()` — a FastAPI dependency that returns a
`CurrentUser` or raises 401. It is intentionally tenant-agnostic; tenant scoping is
layered on top in route handlers via `current_businesses()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helm.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated Supabase user — before we've synced them into our DB."""

    supabase_id: str
    email: str
    raw_claims: dict[str, Any]


@lru_cache(maxsize=1)
def _jwk_client() -> jwt.PyJWKClient:
    settings = get_settings()
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is not configured")
    url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return jwt.PyJWKClient(url, cache_keys=True)


def _decode(token: str) -> dict[str, Any]:
    settings = get_settings()

    # Prefer asymmetric keys via JWKS when the project has them.
    # Fall back to the shared HS256 secret when provided.
    if settings.supabase_jwt_secret:
        return jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": True},
        )

    if not settings.supabase_url:
        raise RuntimeError("Supabase auth not configured (no URL, no JWT secret)")

    signing_key = _jwk_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience="authenticated",
        options={"verify_aud": True},
    )


async def require_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = _decode(creds.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str) or not isinstance(email, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token missing sub or email",
        )

    return CurrentUser(supabase_id=sub, email=email, raw_claims=claims)
