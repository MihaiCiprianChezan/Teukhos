"""Installer for GitHub Copilot / VS Code."""

from __future__ import annotations

import platform
from pathlib import Path

from teukhos.installers.base import InstallScope, JsonMcpInstaller


class GitHubCopilotInstaller(JsonMcpInstaller):
    name = "GitHub Copilot"
    slug = "github-copilot"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    config_key = "servers"
    stdio_needs_type_field = True

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        effective = self._effective_scope(scope)
        if effective == InstallScope.project:
            return self.cwd / ".vscode" / "mcp.json"
        # Global path varies by OS
        system = platform.system()
        if system == "Windows":
            return (
                Path.home() / "AppData" / "Roaming"
                / "Code" / "User" / "mcp.json"
            )
        elif system == "Darwin":
            return (
                Path.home() / "Library" / "Application Support"
                / "Code" / "User" / "mcp.json"
            )
        return Path.home() / ".config" / "Code" / "User" / "mcp.json"
