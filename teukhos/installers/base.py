"""Base installer interface and shared utilities."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class InstallScope(Enum):
    global_ = "global"
    project = "project"


class BaseInstaller(ABC):
    """Abstract base for all client installers."""

    name: str
    slug: str
    supported_scopes: list[InstallScope]

    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd or Path.cwd()

    @abstractmethod
    def detect(self) -> bool:
        """Return True if this client is installed on the system."""

    @abstractmethod
    def config_path(self, scope: InstallScope) -> Path:
        """Return config path for the given scope."""

    def _effective_scope(self, scope: InstallScope) -> InstallScope:
        """Return the effective scope, falling back to global if needed."""
        if scope == InstallScope.project and InstallScope.project not in self.supported_scopes:
            return InstallScope.global_
        return scope

    @abstractmethod
    def install_stdio(self, server_name: str, teukhos_config_path: Path,
                      scope: InstallScope = InstallScope.global_) -> None:
        """Register as stdio MCP server."""

    @abstractmethod
    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        """Register as HTTP MCP server."""

    @abstractmethod
    def uninstall(self, server_name: str,
                  scope: InstallScope = InstallScope.global_) -> None:
        """Remove registration from client config."""


def read_json_config(path: Path) -> dict:
    """Read a JSON config file. Returns {} if file doesn't exist.
    Raises json.JSONDecodeError if file exists but contains invalid JSON.
    """
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to a file atomically with backup."""
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        backup = path.with_suffix(path.suffix + ".teukhos-backup")
        shutil.copy2(path, backup)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp", prefix=path.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def merge_mcp_entry(config: dict, server_name: str, entry: dict,
                    key: str = "mcpServers") -> dict:
    """Merge an MCP server entry into an existing config dict."""
    if key not in config:
        config[key] = {}
    config[key][server_name] = entry
    return config


def remove_mcp_entry(config: dict, server_name: str,
                     key: str = "mcpServers") -> dict:
    """Remove an MCP server entry from a config dict."""
    if key in config:
        config[key].pop(server_name, None)
    return config


class JsonMcpInstaller(BaseInstaller):
    """Concrete base for clients that use a JSON file with mcpServers/servers key.

    Most MCP clients follow this pattern. Subclasses only need to set class
    attributes and implement config_path(). All install/uninstall logic is shared.
    """

    config_key: str = "mcpServers"
    supports_env_substitution: bool = True
    stdio_needs_type_field: bool = False

    _config_path_override: dict[InstallScope, Path] | None = None

    def detect(self) -> bool:
        return self.config_path(InstallScope.global_).parent.exists()

    def install_stdio(self, server_name: str, teukhos_config_path: Path,
                      scope: InstallScope = InstallScope.global_) -> None:
        teukhos_bin = shutil.which("teukhos") or "teukhos"
        effective = self._effective_scope(scope)
        path = self.config_path(effective)
        config = read_json_config(path)
        entry: dict = {
            "command": teukhos_bin,
            "args": ["serve", str(teukhos_config_path)],
        }
        if self.stdio_needs_type_field:
            entry["type"] = "stdio"
        merge_mcp_entry(config, server_name, entry, key=self.config_key)
        atomic_write_json(path, config)

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        effective = self._effective_scope(scope)
        path = self.config_path(effective)
        config = read_json_config(path)
        entry: dict = {"url": url}
        if self.stdio_needs_type_field:
            entry["type"] = "http"
        if api_key:
            if api_key.startswith("env:") and self.supports_env_substitution:
                env_var = api_key[4:]
                entry["headers"] = {"Authorization": f"Bearer ${{{env_var}}}"}
            elif api_key.startswith("env:"):
                from teukhos.auth import resolve_key
                try:
                    resolved = resolve_key(api_key)
                    entry["headers"] = {"Authorization": f"Bearer {resolved}"}
                except ValueError:
                    entry["headers"] = {"Authorization": f"Bearer {api_key}"}
            else:
                entry["headers"] = {"Authorization": f"Bearer {api_key}"}
        merge_mcp_entry(config, server_name, entry, key=self.config_key)
        atomic_write_json(path, config)

    def uninstall(self, server_name: str,
                  scope: InstallScope = InstallScope.global_) -> None:
        effective = self._effective_scope(scope)
        path = self.config_path(effective)
        config = read_json_config(path)
        remove_mcp_entry(config, server_name, key=self.config_key)
        atomic_write_json(path, config)
