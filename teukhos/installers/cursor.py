"""Installer for Cursor."""

from __future__ import annotations

from pathlib import Path

from teukhos.installers.base import InstallScope, JsonMcpInstaller


class CursorInstaller(JsonMcpInstaller):
    name = "Cursor"
    slug = "cursor"
    supported_scopes = [InstallScope.global_, InstallScope.project]

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        effective = self._effective_scope(scope)
        if effective == InstallScope.project:
            return self.cwd / ".cursor" / "mcp.json"
        return Path.home() / ".cursor" / "mcp.json"
