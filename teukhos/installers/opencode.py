"""Installer for OpenCode."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class OpenCodeInstaller(JsonMcpInstaller):
    """OpenCode reads servers from "mcp" (not "mcpServers") and takes the command as one array."""

    name = "OpenCode"
    slug = "opencode"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    config_key = "mcp"

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        effective = self._effective_scope(scope)
        if effective == InstallScope.project:
            return self.cwd / "opencode.json"
        return Path.home() / ".config" / "opencode" / "opencode.json"

    def stdio_entry(self, teukhos_bin: str, teukhos_config_path: Path) -> dict:
        return {"type": "local", "command": [teukhos_bin, "serve", str(teukhos_config_path)]}

    def http_entry(self, url: str, api_key: str | None) -> dict:
        # oauth: false, or a 401 from a bad key starts OpenCode's OAuth discovery
        entry: dict = {"type": "remote", "url": url, "oauth": False}
        if api_key:
            # OpenCode substitutes {env:VAR} (an unset VAR becomes ""); it does not expand ${VAR}
            token = f"{{env:{api_key[4:]}}}" if api_key.startswith("env:") else api_key
            entry["headers"] = {"Authorization": f"Bearer {token}"}
        return entry
