"""Tests for API key resolution and auth middleware."""

import os

import pytest

from teukhos.auth import resolve_key


def test_resolve_literal_key():
    assert resolve_key("my-secret-key-123") == "my-secret-key-123"


def test_resolve_env_key(monkeypatch):
    monkeypatch.setenv("TEUKHOS_API_KEY", "secret-from-env")
    assert resolve_key("env:TEUKHOS_API_KEY") == "secret-from-env"


def test_resolve_env_custom_var(monkeypatch):
    monkeypatch.setenv("MY_CUSTOM_KEY", "custom-secret")
    assert resolve_key("env:MY_CUSTOM_KEY") == "custom-secret"


def test_resolve_env_missing_raises():
    os.environ.pop("NONEXISTENT_KEY_12345", None)
    with pytest.raises(ValueError, match="not set"):
        resolve_key("env:NONEXISTENT_KEY_12345")


def test_resolve_env_empty_raises(monkeypatch):
    monkeypatch.setenv("EMPTY_KEY", "")
    with pytest.raises(ValueError, match="empty"):
        resolve_key("env:EMPTY_KEY")


def test_resolve_empty_string():
    assert resolve_key("") == ""


def test_resolve_env_prefix_only():
    """'env:' with no var name should raise."""
    with pytest.raises(ValueError):
        resolve_key("env:")


from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from teukhos.auth import AuthMiddleware, OriginMiddleware


def _make_app(api_keys: list[str], public_paths: list[str] | None = None):
    """Create a minimal Starlette app with AuthMiddleware for testing."""
    async def homepage(request):
        return PlainTextResponse("ok")

    async def mcp_endpoint(request):
        return PlainTextResponse("mcp ok")

    async def health(request):
        return PlainTextResponse("healthy")

    app = Starlette(routes=[
        Route("/", homepage),
        Route("/mcp", mcp_endpoint),
        Route("/health", health),
    ])
    app.add_middleware(AuthMiddleware, api_keys=api_keys, public_paths=public_paths)
    return TestClient(app)


def test_auth_middleware_valid_key():
    client = _make_app(["secret-123"])
    resp = client.get("/mcp", headers={"Authorization": "Bearer secret-123"})
    assert resp.status_code == 200
    assert resp.text == "mcp ok"


def test_auth_middleware_invalid_key():
    client = _make_app(["secret-123"])
    resp = client.get("/mcp", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_auth_middleware_missing_header():
    client = _make_app(["secret-123"])
    resp = client.get("/mcp")
    assert resp.status_code == 401


def test_auth_middleware_health_not_protected():
    client = _make_app(["secret-123"])
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.text == "healthy"


def test_auth_middleware_other_paths_protected():
    """Deny by default: anything that isn't explicitly public needs a key."""
    client = _make_app(["secret-123"])
    assert client.get("/").status_code == 401
    assert client.get("/", headers={"Authorization": "Bearer secret-123"}).status_code == 200


def test_auth_middleware_custom_public_paths():
    client = _make_app(["secret-123"], public_paths=["/"])
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 401


def test_auth_middleware_multiple_keys():
    client = _make_app(["key-1", "key-2"])
    resp = client.get("/mcp", headers={"Authorization": "Bearer key-2"})
    assert resp.status_code == 200


def test_auth_middleware_empty_keys_denies_all():
    """No keys configured means nobody gets in (fail closed)."""
    client = _make_app([])
    assert client.get("/mcp").status_code == 401
    assert client.get("/mcp", headers={"Authorization": "Bearer "}).status_code == 401


@pytest.mark.parametrize("host", ["a?", "a#", "a/x", "x/../", "127.0.0.1:8765?", "a/health?", "a/health#"])
def test_auth_middleware_host_header_cannot_bypass(host):
    """request.url is rebuilt from the Host header; auth must match the routed path."""
    client = _make_app(["secret-123"])
    resp = client.get("/mcp", headers={"host": host})
    assert resp.status_code == 401


def _make_origin_app(allowed: list[str] | None):
    async def mcp_endpoint(request):
        return PlainTextResponse("mcp ok")

    app = Starlette(routes=[Route("/mcp", mcp_endpoint, methods=["GET", "POST"])])
    app.add_middleware(OriginMiddleware, allowed_origins=allowed)
    return TestClient(app)


def test_origin_middleware_no_origin_header_allowed():
    """Non-browser MCP clients send no Origin and must not be affected."""
    assert _make_origin_app(None).post("/mcp").status_code == 200


@pytest.mark.parametrize("origin", ["http://rebind.evil.example:8765", "null"])
def test_origin_middleware_rejects_foreign_origin(origin):
    client = _make_origin_app(["https://app.example"])
    assert client.post("/mcp", headers={"origin": origin}).status_code == 403


def test_origin_middleware_allows_listed_origin():
    client = _make_origin_app(["https://app.example"])
    assert client.post("/mcp", headers={"origin": "https://app.example"}).status_code == 200


def test_origin_middleware_wildcard_allows_any():
    client = _make_origin_app(["*"])
    assert client.post("/mcp", headers={"origin": "https://anything.example"}).status_code == 200


from teukhos.config import ForgeConfig, ForgeInfo, AuthConfig, AuthMode
from teukhos.engine import build_server


def test_build_server_with_auth_returns_resolved_keys(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "test-secret")
    config = ForgeConfig(
        forge=ForgeInfo(name="test-auth"),
        auth=AuthConfig(mode=AuthMode.api_key, api_keys=["env:TEST_KEY"]),
        tools=[],
    )
    result = build_server(config)
    assert result.resolved_auth_keys == ["test-secret"]
    assert result.mcp is not None


def test_build_server_no_auth_returns_empty_keys():
    config = ForgeConfig(
        forge=ForgeInfo(name="test-no-auth"),
        tools=[],
    )
    result = build_server(config)
    assert result.resolved_auth_keys == []
