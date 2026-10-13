"""Installer for Claude Code."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class ClaudeCodeInstaller(JsonMcpInstaller):
    name = "Claude Code"
    slug = "claude-code"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    http_type = "http"  # an entry without "type" is read as stdio

    def detect(self) -> bool:
        return (Path.home() / ".claude").exists() or (Path.home() / ".claude.json").exists()

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".mcp.json"  # project servers live here, not in .claude/settings.json
        return Path.home() / ".claude.json"
