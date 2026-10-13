"""Installer for Claude Desktop."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from teukhos.installers.base import InstallScope, JsonMcpInstaller


class ClaudeDesktopInstaller(JsonMcpInstaller):
    name = "Claude Desktop"
    slug = "claude-desktop"
    supported_scopes = [InstallScope.global_]
    supports_env_substitution = False

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        system = platform.system()
        if system == "Darwin":
            return (
                Path.home() / "Library" / "Application Support"
                / "Claude" / "claude_desktop_config.json"
            )
        elif system == "Windows":
            appdata = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
            return Path(appdata) / "Claude" / "claude_desktop_config.json"
        config_home = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        return Path(config_home) / "Claude" / "claude_desktop_config.json"

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        # Claude Desktop skips url entries in this file (and then drops them on its next write)
        raise ValueError(
            "Claude Desktop's config file only supports local (stdio) servers. Install without --url, "
            "or add a public HTTPS server under Customize > Connectors in Claude Desktop."
        )
