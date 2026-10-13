"""Installer for Devin Desktop (formerly Windsurf)."""
from __future__ import annotations
import platform
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller, app_data_dir, xdg_config_dir

class DevinInstaller(JsonMcpInstaller):
    name = "Devin Desktop (Windsurf)"
    slug = "devin"
    supported_scopes = [InstallScope.global_, InstallScope.project]
    env_ref = "${{env:{}}}"

    def detect(self) -> bool:
        return (self.default_path(InstallScope.global_).parent.exists()
                or (Path.home() / ".codeium" / "windsurf").exists())

    def default_path(self, scope: InstallScope) -> Path:
        if scope == InstallScope.project:
            return self.cwd / ".devin" / "mcp_config.json"
        base = app_data_dir() if platform.system() == "Windows" else xdg_config_dir()
        return base / "devin" / "mcp_config.json"
