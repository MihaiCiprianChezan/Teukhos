"""Installer for Claude Desktop."""

from __future__ import annotations

from pathlib import Path

from teukhos.installers.base import InstallScope, JsonMcpInstaller, app_data_dir


class ClaudeDesktopInstaller(JsonMcpInstaller):
    name = "Claude Desktop"
    slug = "claude-desktop"
    supported_scopes = [InstallScope.global_]

    def default_path(self, scope: InstallScope) -> Path:
        return app_data_dir() / "Claude" / "claude_desktop_config.json"

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        # Claude Desktop skips url entries in this file (and then drops them on its next write)
        raise ValueError(
            "Claude Desktop's config file only supports local (stdio) servers. Install without --url, "
            "or add a public HTTPS server under Customize > Connectors in Claude Desktop."
        )
