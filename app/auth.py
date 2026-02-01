"""Clerk JWKS authentication for RAG Service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import cachetools
import httpx
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt


@dataclass
class AuthenticatedUser:
    """Authenticated user from Clerk JWT."""
    user_id: str
    email: Optional[str]
    claims: Dict[str, Any]


# JWKS cache with 1-hour TTL
_JWKS_CACHE: cachetools.TTLCache[str, Dict[str, Any]] = cachetools.TTLCache(maxsize=1, ttl=3600)

# Security scheme
security = HTTPBearer(auto_error=False)


class AuthError(Exception):
    """Raised when token validation fails."""


def get_jwks_url() -> str:
    """
    Get JWKS URL from environment.
    Priority: GLOBAL_AUTH_JWKS_URL > derive from CLERK_FRONTEND_API
    """
    # Try explicit JWKS URL first
    jwks_url = os.getenv("GLOBAL_AUTH_JWKS_URL")
    if jwks_url:
        return jwks_url

    # Fallback: derive from Clerk frontend API
    clerk_frontend_api = os.getenv("CLERK_FRONTEND_API")
    if clerk_frontend_api:
        host = clerk_frontend_api.replace("https://", "").replace("http://", "").strip("/")
        return f"https://{host}/.well-known/jwks.json"

    raise AuthError("GLOBAL_AUTH_JWKS_URL or CLERK_FRONTEND_API must be configured")


async def _fetch_jwks() -> Dict[str, Any]:
    """Fetch JWKS from Clerk with caching."""
    cached = _JWKS_CACHE.get("jwks")
    if cached:
        return cached

    jwks_url = get_jwks_url()

    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(jwks_url)
        response.raise_for_status()
        jwks = response.json()
        _JWKS_CACHE["jwks"] = jwks
        return jwks


async def verify_clerk_token(token: str) -> AuthenticatedUser:
    """
    Verify Clerk JWT token and return authenticated user.

    Args:
        token: JWT token from Authorization header

    Returns:
        AuthenticatedUser with user_id, email, and claims

    Raises:
        AuthError: If token is invalid or verification fails
    """
    if not token:
        raise AuthError("Missing bearer token")

    try:
        unverified_header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise AuthError("Invalid token header") from exc

    # Fetch JWKS and find matching key
    jwks = await _fetch_jwks()
    key = next(
        (k for k in jwks.get("keys", []) if k.get("kid") == unverified_header.get("kid")),
        None
    )
    if not key:
        raise AuthError("Unable to find matching JWK")

    # Decode and verify token
    # Get expected audience from env (Clerk instance URL or custom)
    audience = os.getenv("CLERK_JWT_AUDIENCE")
    if not audience and os.getenv("CLERK_FRONTEND_API"):
        # Deriving audience from frontend API is only for production
        if os.getenv("ENVIRONMENT") == "production":
            audience = os.getenv("CLERK_FRONTEND_API", "").replace("https://", "").replace("http://", "").strip("/")

    # Get expected issuer (should be the Clerk frontend API)
    issuer = os.getenv("CLERK_JWT_ISSUER")
    if not issuer and os.getenv("CLERK_FRONTEND_API"):
        if os.getenv("ENVIRONMENT") == "production":
            issuer = os.getenv("CLERK_FRONTEND_API", "").replace("https://", "").replace("http://", "").strip("/")
            issuer = f"https://{issuer}"

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],  # Clerk uses RS256
            audience=audience if audience else None,
            issuer=issuer if issuer else None,
            options={
                "verify_aud": bool(audience),
                "verify_iss": bool(issuer),
                "leeway": 600  # 10 minutes leeway for clock skew
            }
        )
    except Exception as exc:
        raise AuthError(f"Token validation failed: {exc}") from exc

    # Extract user ID
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise AuthError("Token missing subject")

    return AuthenticatedUser(
        user_id=user_id,
        email=claims.get("email"),
        claims=claims
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency for route protection.
    Checks request.state.user first (set by middleware), then falls back to token.

    Usage:
        @app.get("/protected")
        async def protected_route(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """
    # 1. Check if middleware already authenticated the user
    if hasattr(request.state, "user") and request.state.user:
        user_data = request.state.user
        return AuthenticatedUser(
            user_id=user_data.get("user_id"),
            email=user_data.get("email"),
            claims=user_data.get("claims", {})
        )

    # 2. Fallback to manual token validation (useful if middleware is bypassed/disabled)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await verify_clerk_token(credentials.credentials)
        return user
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthenticatedUser]:
    """
    FastAPI dependency for optional authentication.
    Returns None if no credentials provided, otherwise validates token.
    """
    if not credentials:
        return None

    try:
        user = await verify_clerk_token(credentials.credentials)
        return user
    except AuthError:
        return None
