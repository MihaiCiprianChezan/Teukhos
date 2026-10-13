"""Installer for Continue.dev (no longer maintained since joining Cursor in 2026-06)."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class ContinueDevInstaller(JsonMcpInstaller):
    name = "Continue.dev"
    slug = "continue"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    env_ref = None  # headers are sent verbatim

    def detect(self) -> bool:
        return (Path.home() / ".continue").exists()

    def default_path(self, scope: InstallScope) -> Path:
        # Continue only scans mcpServers/ folders, not ~/.continue/mcp.json
        root = self.cwd if scope == InstallScope.project else Path.home()
        return root / ".continue" / "mcpServers" / "mcp.json"
