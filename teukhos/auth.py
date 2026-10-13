"""API key resolution and authentication utilities."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


def claims_user(claims: dict, subject: str | None = None) -> str | None:
    """The caller's name from token claims: email where the provider has one, else login/subject."""
    for name in ("email", "upn", "preferred_username", "login"):
        if claims.get(name):
            return str(claims[name])
    return subject


def current_user() -> str | None:
    """The authenticated caller of the current MCP request (OAuth modes), or None."""
    from fastmcp.server.dependencies import get_access_token

    token = get_access_token()
    return claims_user(token.claims or {}, token.subject) if token else None


def resolve_key(value: str) -> str:
    """Resolve an API key value.

    If the value starts with 'env:', read from the named environment variable.
    Otherwise, use the value as a literal key.

    Raises:
        ValueError: If env var is referenced but not set or empty, or if env:
            prefix has no variable name.
    """
    if value.startswith("env:"):
        env_var = value[4:]
        if not env_var:
            raise ValueError("env: prefix requires a variable name (e.g., 'env:TEUKHOS_API_KEY')")
        key = os.environ.get(env_var)
        if key is None:
            raise ValueError(f"Environment variable '{env_var}' is not set")
        if not key:
            raise ValueError(f"Environment variable '{env_var}' is set but empty")
        return key
    return value


class AuthMiddleware(BaseHTTPMiddleware):
    """Bearer token authentication middleware.

    Every path except the public ones (default: /health) requires a valid key;
    an empty key list denies everything. Paths are matched on scope["path"],
    which the router uses; request.url is rebuilt from the client-controlled
    Host header and must not be used for access decisions.
    """

    def __init__(self, app, api_keys: list[str], public_paths: list[str] | None = None):
        super().__init__(app)
        self.api_keys = set(api_keys)
        self.public_paths = set(["/health"] if public_paths is None else public_paths)

    async def dispatch(self, request: Request, call_next):
        if request.scope["path"] in self.public_paths:
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"},
                status_code=401,
            )

        token = auth_header[7:]  # Strip "Bearer "
        if token not in self.api_keys:
            return JSONResponse(
                {"error": "Invalid API key"},
                status_code=401,
            )

        return await call_next(request)


class OriginMiddleware(BaseHTTPMiddleware):
    """Reject browser requests from origins not listed in cors_origins.

    Blocks DNS rebinding and cross-site calls to a local server (the MCP spec
    requires servers to validate Origin). Clients that send no Origin header,
    i.e. non-browser MCP clients, are not affected.
    """

    def __init__(self, app, allowed_origins: list[str] | None = None):
        super().__init__(app)
        self.allowed_origins = set(allowed_origins or [])

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and "*" not in self.allowed_origins and origin not in self.allowed_origins:
            return JSONResponse({"error": "Origin not allowed"}, status_code=403)
        return await call_next(request)
