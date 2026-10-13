"""Base installer interface and shared utilities."""

from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path


class InstallScope(Enum):
    global_ = "global"
    project = "project"


def xdg_config_dir() -> Path:
    """$XDG_CONFIG_HOME, or ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def app_data_dir() -> Path:
    """Per-user app data: %APPDATA% on Windows, ~/Library/Application Support on macOS, else XDG."""
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support"
    return xdg_config_dir()


class BaseInstaller(ABC):
    """Abstract base for all client installers."""

    name: str
    slug: str
    supported_scopes: list[InstallScope]

    _config_path_override: dict[InstallScope, Path] | None = None  # tests point installers at temp files

    def __init__(self, cwd: Path | None = None):
        self.cwd = cwd or Path.cwd()

    @abstractmethod
    def detect(self) -> bool:
        """Return True if this client is installed on the system."""

    def config_path(self, scope: InstallScope) -> Path:
        """Config file for the scope (project falls back to global when the client has none)."""
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        return self.default_path(self._effective_scope(scope))

    @abstractmethod
    def default_path(self, scope: InstallScope) -> Path:
        """Where the client reads its MCP config for an (effective) scope."""

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


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to a file atomically with backup. New files get mode 0600 (mkstemp)."""
    # Dotfiles setups: update the file a symlink points to instead of replacing the link.
    # Dangling links are replaced as before, so a planted link can't create files elsewhere.
    if path.is_symlink() and path.exists():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        backup = path.with_suffix(path.suffix + ".teukhos-backup")
        shutil.copy2(path, backup)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, suffix=".tmp", prefix=path.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to a file atomically with backup."""
    atomic_write_text(path, json.dumps(data, indent=2) + "\n")


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

    Most MCP clients follow this pattern. Subclasses set the class attributes
    below and implement default_path(). All install/uninstall logic is shared.
    """

    config_key: str = "mcpServers"
    stdio_type: str | None = None  # "type" for stdio entries, if the client wants one
    http_type: str | None = None   # "type" for remote entries ("http", "streamableHttp", ...); None: url only
    # How the client spells an env var reference in headers, as a format string
    # ("${{{}}}" -> ${VAR}, "${{env:{}}}" -> ${env:VAR}); None: it can't, so resolve the key at install.
    env_ref: str | None = "${{{}}}"

    def detect(self) -> bool:
        return self.config_path(InstallScope.global_).parent.exists()

    def api_key_ref(self, api_key: str) -> str:
        """The API key as the client should see it: an env reference it expands, or the value."""
        if not api_key.startswith("env:"):
            return api_key
        if self.env_ref:
            return self.env_ref.format(api_key[4:])
        from teukhos.auth import resolve_key
        # Fail loudly rather than write "Bearer env:VAR"; the resolved key is stored in plain text
        return resolve_key(api_key)

    def stdio_entry(self, teukhos_bin: str, teukhos_config_path: Path) -> dict:
        entry: dict = {
            "command": teukhos_bin,
            "args": ["serve", str(teukhos_config_path)],
        }
        if self.stdio_type:
            entry["type"] = self.stdio_type
        return entry

    def http_entry(self, url: str, api_key: str | None) -> dict:
        entry: dict = {"type": self.http_type, "url": url} if self.http_type else {"url": url}
        if api_key:
            entry["headers"] = {"Authorization": f"Bearer {self.api_key_ref(api_key)}"}
        return entry

    def install_stdio(self, server_name: str, teukhos_config_path: Path,
                      scope: InstallScope = InstallScope.global_) -> None:
        teukhos_bin = shutil.which("teukhos") or "teukhos"
        path = self.config_path(self._effective_scope(scope))
        config = read_json_config(path)
        merge_mcp_entry(config, server_name, self.stdio_entry(teukhos_bin, teukhos_config_path),
                        key=self.config_key)
        atomic_write_json(path, config)

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        path = self.config_path(self._effective_scope(scope))
        config = read_json_config(path)
        merge_mcp_entry(config, server_name, self.http_entry(url, api_key), key=self.config_key)
        atomic_write_json(path, config)

    def uninstall(self, server_name: str,
                  scope: InstallScope = InstallScope.global_) -> None:
        effective = self._effective_scope(scope)
        path = self.config_path(effective)
        if not path.exists():
            return  # don't create a config (and make the client look installed) just to remove from it
        config = read_json_config(path)
        remove_mcp_entry(config, server_name, key=self.config_key)
        atomic_write_json(path, config)


class DestInstaller(JsonMcpInstaller):
    """`install --dest`: any JSON file; "servers" selects the VS Code format."""

    name = "Custom file"
    slug = "dest"
    supported_scopes = [InstallScope.global_]

    def __init__(self, path: Path, config_key: str = "mcpServers"):
        super().__init__()
        self.path = path
        self.config_key = config_key
        if config_key == "servers":  # VS Code format: typed entries, ${env:VAR}
            self.stdio_type, self.http_type, self.env_ref = "stdio", "http", "${{env:{}}}"

    def default_path(self, scope: InstallScope) -> Path:
        return self.path
