"""Installer for OpenCode."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller, xdg_config_dir

class OpenCodeInstaller(JsonMcpInstaller):
    """OpenCode reads servers from "mcp" (not "mcpServers") and takes the command as one array."""

    name = "OpenCode"
    slug = "opencode"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    config_key = "mcp"

    env_ref = "{{env:{}}}"  # OpenCode substitutes {env:VAR} (unset -> ""); it does not expand ${VAR}

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / "opencode.json"
        return xdg_config_dir() / "opencode" / "opencode.json"

    def stdio_entry(self, teukhos_bin: str, teukhos_config_path: Path) -> dict:
        return {"type": "local", "command": [teukhos_bin, "serve", str(teukhos_config_path)]}

    def http_entry(self, url: str, api_key: str | None) -> dict:
        entry: dict = {"type": "remote", "url": url}
        if api_key:
            # oauth: false, or a 401 from a bad key starts OpenCode's OAuth discovery; without a key
            # (an OAuth server) OpenCode runs its own login
            entry["oauth"] = False
            entry["headers"] = {"Authorization": f"Bearer {self.api_key_ref(api_key)}"}
        return entry
