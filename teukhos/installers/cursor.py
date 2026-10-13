"""Installer for Cursor."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class CursorInstaller(JsonMcpInstaller):
    name = "Cursor"
    slug = "cursor"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    stdio_type = "stdio"
    env_ref = "${{env:{}}}"

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".cursor" / "mcp.json"
        return Path.home() / ".cursor" / "mcp.json"
