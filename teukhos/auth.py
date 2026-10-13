"""API key resolution and authentication utilities."""

from __future__ import annotations

import os

from fastmcp.server.auth import AuthProvider
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from teukhos.config import OAuthConfig, OAuthProviderType


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


# Where MCP clients may send users back after login. Without a list any redirect_uri is
# accepted and the consent screen is the only defence. Loopback covers Claude Code, Codex,
# LM Studio and the MCP Inspector; add others (e.g. Open WebUI) with auth.oauth.redirect_uris.
DEFAULT_CLIENT_REDIRECT_URIS = [
    "https://claude.ai/api/mcp/auth_callback",
    "https://chatgpt.com/connector_platform_oauth_redirect",
    "https://chatgpt.com/connector/oauth/*",
    "http://localhost:*",
    "http://127.0.0.1:*",
]


def build_oauth_provider(oauth: OAuthConfig, public_url: str) -> AuthProvider:
    """fastmcp's OAuth proxy for the configured identity provider. Teukhos becomes the OAuth
    server that ChatGPT/Claude talk to; the provider needs one redirect URI: <public_url>/auth/callback."""
    common = dict(
        client_id=resolve_key(oauth.client_id),
        base_url=public_url,
        jwt_signing_key=resolve_key(oauth.signing_key),
        allowed_client_redirect_uris=DEFAULT_CLIENT_REDIRECT_URIS + oauth.redirect_uris,
        require_authorization_consent=oauth.consent,
    )
    secret = resolve_key(oauth.client_secret) if oauth.client_secret else None
    match oauth.provider:
        case OAuthProviderType.entra:
            from fastmcp.server.auth.providers.azure import AzureProvider
            return AzureProvider(client_secret=secret, tenant_id=oauth.tenant_id, required_scopes=[oauth.scope],
                                 additional_authorize_scopes=["openid", "profile", "email"], **common)
        case OAuthProviderType.google:
            from fastmcp.server.auth.providers.google import GoogleProvider
            # Google tokens are re-checked against Google per request; cache that for 5 minutes
            return GoogleProvider(client_secret=secret, required_scopes=["openid", "email", "profile"],
                                  cache_ttl_seconds=300, **common)
        case OAuthProviderType.github:
            from fastmcp.server.auth.providers.github import GitHubProvider
            # read:user is all Teukhos needs (fastmcp's default 'user' can write the profile)
            return GitHubProvider(client_secret=secret, required_scopes=["read:user"], cache_ttl_seconds=300,
                                  **common)
        case OAuthProviderType.oidc:
            from fastmcp.server.auth.oidc_proxy import OIDCProxy
            scopes = ["openid", "email", "profile"]
            requested = [*scopes, "offline_access", *oauth.extra_scopes]
            # Fetches the provider's discovery document now, so the IdP must be reachable at startup.
            # Clients usually ask only for the required scopes, so force the full set upstream
            # (e.g. Okta's 'groups'), while tokens are only required to carry the OIDC ones.
            return OIDCProxy(config_url=oauth.config_url, client_secret=secret, verify_id_token=oauth.verify_id_token,
                             required_scopes=scopes, valid_scopes=requested,
                             extra_authorize_params={"scope": " ".join(requested)}, **common)


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
