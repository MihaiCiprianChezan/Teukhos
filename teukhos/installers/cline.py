"""Installer for Cline (VS Code extension, CLI and JetBrains share one settings file)."""
from __future__ import annotations
import os
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller

class ClineInstaller(JsonMcpInstaller):
    name = "Cline"
    slug = "cline"
    supported_scopes = [InstallScope.global_]
    http_type = "streamableHttp"  # without a type Cline falls back to legacy SSE
    env_ref = "${{env:{}}}"

    def default_path(self, scope: InstallScope) -> Path:
        if os.environ.get("CLINE_MCP_SETTINGS_PATH"):
            return Path(os.environ["CLINE_MCP_SETTINGS_PATH"])
        if os.environ.get("CLINE_DATA_DIR"):
            return Path(os.environ["CLINE_DATA_DIR"]) / "settings" / "cline_mcp_settings.json"
        cline_dir = Path(os.environ.get("CLINE_DIR") or Path.home() / ".cline")
        return cline_dir / "data" / "settings" / "cline_mcp_settings.json"
