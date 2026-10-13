"""Installer for Roo Code (discontinued 2026-05; existing installs keep working)."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller, app_data_dir

class RooCodeInstaller(JsonMcpInstaller):
    name = "Roo Code"
    slug = "roo-code"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    http_type = "streamable-http"
    env_ref = "${{env:{}}}"

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".roo" / "mcp.json"
        return (app_data_dir() / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline"
                / "settings" / "mcp_settings.json")
