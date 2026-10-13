"""Installer for GitHub Copilot in VS Code."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller, app_data_dir

class GitHubCopilotInstaller(JsonMcpInstaller):
    name = "GitHub Copilot"
    slug = "github-copilot"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    config_key = "servers"
    stdio_type = "stdio"
    http_type = "http"
    env_ref = "${{env:{}}}"  # VS Code variable syntax; a bare ${VAR} is sent literally

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".vscode" / "mcp.json"
        return app_data_dir() / "Code" / "User" / "mcp.json"
