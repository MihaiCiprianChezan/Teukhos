"""Installer for Trae."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller, app_data_dir

class TraeInstaller(JsonMcpInstaller):
    name = "Trae"
    slug = "trae"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    env_ref = None  # only ${workspaceFolder} is substituted

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".trae" / "mcp.json"  # loads once 'Project MCP' is enabled in Trae
        return app_data_dir() / "Trae" / "User" / "mcp.json"
