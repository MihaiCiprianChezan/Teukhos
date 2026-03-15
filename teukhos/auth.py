"""API key resolution and authentication utilities."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


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

    Only protects specified paths (default: /mcp). Health and other
    endpoints pass through. When api_keys is empty, all requests are allowed.
    """

    def __init__(self, app, api_keys: list[str], protected_paths: list[str] | None = None):
        super().__init__(app)
        self.api_keys = set(api_keys)
        self.protected_paths = set(protected_paths or ["/mcp"])

    async def dispatch(self, request: Request, call_next):
        if not self.api_keys or request.url.path not in self.protected_paths:
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
