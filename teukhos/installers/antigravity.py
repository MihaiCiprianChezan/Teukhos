"""Installer for Google Antigravity (Gemini CLI's successor for consumer plans)."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class AntigravityInstaller(JsonMcpInstaller):
    name = "Antigravity"
    slug = "antigravity"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    env_ref = None  # header variable expansion is not documented

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".agents" / "mcp_config.json"
        return Path.home() / ".gemini" / "config" / "mcp_config.json"

    def http_entry(self, url: str, api_key: str | None) -> dict:
        entry: dict = {"serverUrl": url}  # Antigravity reads serverUrl, not url
        if api_key:
            entry["headers"] = {"Authorization": f"Bearer {self.api_key_ref(api_key)}"}
        return entry
