"""Installer for Gemini CLI."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import (
    InstallScope,
    JsonMcpInstaller,
    atomic_write_json,
    merge_mcp_entry,
    read_json_config,
)

class GeminiCLIInstaller(JsonMcpInstaller):
    name = "Gemini CLI"
    slug = "gemini-cli"
    supported_scopes = [InstallScope.global_, InstallScope.project]

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".gemini" / "settings.json"
        return Path.home() / ".gemini" / "settings.json"

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        path = self.config_path(self._effective_scope(scope))
        config = read_json_config(path)
        merge_mcp_entry(config, server_name, self.http_entry(url, api_key), key=self.config_key)
        if api_key and api_key.startswith("env:"):
            # Gemini expands header variables from a filtered environment that drops names
            # containing KEY/TOKEN/SECRET/AUTH...; allowlist ours or the header goes out empty
            redaction = config.setdefault("security", {}).setdefault("environmentVariableRedaction", {})
            allowed = redaction.setdefault("allowed", [])
            if api_key[4:] not in allowed:
                allowed.append(api_key[4:])
        atomic_write_json(path, config)
