"""Installer for CodeBuddy."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class CodeBuddyInstaller(JsonMcpInstaller):
    name = "CodeBuddy"
    slug = "codebuddy"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    stdio_type = "stdio"
    http_type = "http"

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".mcp.json"
        return Path.home() / ".codebuddy" / ".mcp.json"
