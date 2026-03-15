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

from teukhos.auth import AuthMiddleware


def _make_app(api_keys: list[str], protected_paths: list[str] | None = None):
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
    app.add_middleware(
        AuthMiddleware,
        api_keys=api_keys,
        protected_paths=protected_paths or ["/mcp"],
    )
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


def test_auth_middleware_unprotected_path():
    client = _make_app(["secret-123"])
    resp = client.get("/")
    assert resp.status_code == 200


def test_auth_middleware_multiple_keys():
    client = _make_app(["key-1", "key-2"])
    resp = client.get("/mcp", headers={"Authorization": "Bearer key-2"})
    assert resp.status_code == 200


def test_auth_middleware_empty_keys_allows_all():
    """When no keys configured, middleware should not block."""
    client = _make_app([])
    resp = client.get("/mcp")
    assert resp.status_code == 200


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
