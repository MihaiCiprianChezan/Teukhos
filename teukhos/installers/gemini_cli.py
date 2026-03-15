"""Installer for Gemini CLI."""

from __future__ import annotations

from pathlib import Path

from teukhos.installers.base import InstallScope, JsonMcpInstaller


class GeminiCLIInstaller(JsonMcpInstaller):
    name = "Gemini CLI"
    slug = "gemini-cli"
    supported_scopes = [InstallScope.global_]

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        return Path.home() / ".gemini" / "settings.json"
