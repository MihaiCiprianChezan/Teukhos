"""Installer for Augment Code (Auggie)."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class AuggieInstaller(JsonMcpInstaller):
    name = "Augment Code"
    slug = "augment"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    env_ref = None  # only ${workspaceFolder} is substituted

    def default_path(self, scope: InstallScope) -> Path:
        root = self.cwd if scope == InstallScope.project else Path.home()
        return root / ".augment" / "settings.json"
