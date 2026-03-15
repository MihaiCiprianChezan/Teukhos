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
