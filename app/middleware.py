"""
Global Authentication Middleware for EmailPilot RAG Spoke.
Enforces Clerk authentication and EmailPilot internal service key validation.
"""
import os
import logging
from typing import Optional, Dict, Any, List, Set
from fastapi import Request, HTTPException, status, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import quote

from app.auth import verify_clerk_token

logger = logging.getLogger(__name__)

# Internal Service User DTO
INTERNAL_SERVICE_USER = {
    "user_id": "internal-service",
    "email": "internal@emailpilot.local",
    "display_name": "Internal Service",
    "roles": ["super_admin"],
    "is_internal_service": True
}

class GlobalAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces authentication on all non-public paths.
    Supports Clerk RS256 tokens and Internal Service Keys.
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.enabled = os.getenv("GLOBAL_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
        self.internal_service_key = os.getenv("INTERNAL_SERVICE_KEY")
        
        # Public paths that don't require authentication
        self.public_paths: Set[str] = {
            "/",
            "/health",
            "/rag/health",
            "/api/health",
            "/api/v1/health",
            "/auth/config",
            "/favicon.ico"
        }
        
        # Public path prefixes
        self.public_prefixes: List[str] = [
            "/ui",
            "/rag/ui",
            "/static",
            "/rag/static",
        ]

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        path = request.url.path
        
        # 1. Check if path is public
        if path in self.public_paths:
            return await call_next(request)
            
        for prefix in self.public_prefixes:
            if path.startswith(prefix):
                # We still might want to protect UI, but usually we let the JS handle it
                # For consistency with other spokes:
                return await call_next(request)

        # 2. Check for Internal Service Key (X-Internal-Service-Key)
        svc_key = request.headers.get("X-Internal-Service-Key")
        if svc_key and self.internal_service_key and svc_key == self.internal_service_key:
            request.state.user = INTERNAL_SERVICE_USER
            return await call_next(request)

        # 3. Check for Authorization header
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

        # 4. Check for shared session cookie (Single Sign-On)
        if not token:
            token = request.cookies.get("emailpilot_clerk_jwt")

        if not token:
            return self._unauthorized_response(request)

        # 5. Verify Token
        try:
            user = await verify_clerk_token(token)
            request.state.user = {
                "user_id": user.user_id,
                "email": user.email,
                "claims": user.claims
            }
            return await call_next(request)
        except Exception as e:
            logger.warning(f"Auth verification failed: {str(e)}")
            return self._unauthorized_response(request)

    def _unauthorized_response(self, request: Request) -> Response:
        # If it's an API request, return 401
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required", "code": "unauthorized"},
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # If it's a page request, redirect to Hub Login
        current_url = str(request.url)
        # Use the central Hub Login
        login_url = f"https://app.emailpilot.ai/static/login.html?returnUrl={quote(current_url)}&reason=unauthorized"
        
        return Response(
            content=f'<html><script>window.location.href="{login_url}"</script></html>',
            media_type="text/html",
            status_code=status.HTTP_401_UNAUTHORIZED
        )
