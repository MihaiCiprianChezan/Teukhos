"""Tests for the serve command's startup security checks (FastMCP.run is stubbed)."""

import pytest
from fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware
from typer.testing import CliRunner

from teukhos.auth import AuthMiddleware, OriginMiddleware
from teukhos.cli import app

runner = CliRunner()


@pytest.fixture
def run_calls(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(FastMCP, "run", lambda self, **kwargs: calls.append(kwargs))
    return calls


def _serve(tmp_path, body: str, *extra: str):
    path = tmp_path / "teukhos.yaml"
    path.write_text("forge:\n  name: t\n" + body + "tools: []\n", encoding="utf-8")
    return runner.invoke(app, ["serve", str(path), *extra])


def _middleware(run_calls) -> list[type]:
    return [m.cls for m in run_calls[0]["middleware"]]


def test_api_key_without_resolvable_key_refuses_to_start(tmp_path, run_calls, monkeypatch):
    monkeypatch.delenv("TEUKHOS_TEST_UNSET_KEY", raising=False)
    result = _serve(tmp_path, (
        "server:\n  transport: http\n"
        "auth:\n  mode: api_key\n  api_keys: ['env:TEUKHOS_TEST_UNSET_KEY']\n"
    ))
    assert result.exit_code == 1
    assert "Refusing to start" in result.output
    assert run_calls == []


def test_api_key_unresolved_still_serves_stdio(tmp_path, run_calls, monkeypatch):
    """Auth only applies to HTTP; a shared config must keep working over stdio."""
    monkeypatch.delenv("TEUKHOS_TEST_UNSET_KEY", raising=False)
    result = _serve(tmp_path, "auth:\n  mode: api_key\n  api_keys: ['env:TEUKHOS_TEST_UNSET_KEY']\n")
    assert result.exit_code == 0
    assert run_calls == [{"transport": "stdio"}]


def test_http_middleware_order(tmp_path, run_calls, monkeypatch):
    monkeypatch.setenv("TEUKHOS_TEST_KEY", "k")
    result = _serve(tmp_path, (
        "server:\n  transport: http\n  cors_origins: ['https://app.example']\n"
        "auth:\n  mode: api_key\n  api_keys: ['env:TEUKHOS_TEST_KEY']\n"
    ))
    assert result.exit_code == 0, result.output
    assert _middleware(run_calls) == [OriginMiddleware, CORSMiddleware, AuthMiddleware]


def test_http_without_auth_or_cors_still_checks_origin(tmp_path, run_calls):
    result = _serve(tmp_path, "server:\n  transport: http\n")
    assert result.exit_code == 0, result.output
    assert _middleware(run_calls) == [OriginMiddleware]
    assert "Security Warning" not in result.output


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.50"])
def test_network_bind_without_auth_warns(tmp_path, run_calls, host):
    result = _serve(tmp_path, f"server:\n  transport: http\n  host: '{host}'\n")
    assert result.exit_code == 0, result.output
    assert "Security Warning" in result.output


def test_cors_wildcard_without_auth_warns(tmp_path, run_calls):
    result = _serve(tmp_path, "server:\n  transport: http\n  cors_origins: ['*']\n")
    assert "any website" in result.output.lower()


def test_markup_in_names_does_not_crash(tmp_path, run_calls):
    path = tmp_path / "teukhos.yaml"
    path.write_text("forge:\n  name: 'tools[/bold]'\ntools: []\n", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0, result.output
    assert "tools[/bold]" in result.output


def test_discover_error_with_markup_in_path():
    result = runner.invoke(app, ["discover", "nope/[/x]/no-such-tool"])
    assert result.exit_code == 1
    assert "nope/[/x]/no-such-tool" in result.output
    assert "Could not get --help output" in result.output
