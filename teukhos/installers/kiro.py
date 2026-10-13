"""Installer for Kiro."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class KiroInstaller(JsonMcpInstaller):
    name = "Kiro"
    slug = "kiro"
    supported_scopes = [InstallScope.global_, InstallScope.project]

    def default_path(self, scope: InstallScope) -> Path:
        root = self.cwd if scope == InstallScope.project else Path.home()
        return root / ".kiro" / "settings" / "mcp.json"
