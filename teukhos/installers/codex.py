"""Installer for OpenAI Codex CLI."""

from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path

from teukhos.installers.base import BaseInstaller, InstallScope, atomic_write_text


def _toml_str(value: object) -> str:
    """TOML basic string. JSON escapes are valid TOML escapes; DEL is the one extra TOML forbids raw."""
    return json.dumps(str(value), ensure_ascii=False).replace("\x7f", "\\u007f")


def _toml_key(name: str) -> str:
    """Bare key when possible (keeps existing entries byte-identical), quoted otherwise."""
    return name if re.fullmatch(r"[A-Za-z0-9_-]+", name) else _toml_str(name)


def _keep_trailing_comments(match: re.Match) -> str:
    """Drop a removed table but keep the comment/blank lines at its end: they introduce the next table."""
    lines = match.group(0).splitlines(keepends=True)
    keep: list[str] = []
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        keep.insert(0, lines.pop())
    return "".join(keep) if any(line.strip() for line in keep) else ""


class CodexInstaller(BaseInstaller):
    name = "Codex"
    slug = "codex"
    supported_scopes = [InstallScope.global_, InstallScope.project]

    _config_path_override: dict[InstallScope, Path] | None = None

    def detect(self) -> bool:
        return self.config_path(InstallScope.global_).parent.exists()

    def config_path(self, scope: InstallScope) -> Path:
        if self._config_path_override and scope in self._config_path_override:
            return self._config_path_override[scope]
        effective = self._effective_scope(scope)
        if effective == InstallScope.project:
            return self.cwd / ".codex" / "config.toml"
        return Path.home() / ".codex" / "config.toml"

    def install_stdio(self, server_name: str, teukhos_config_path: Path,
                      scope: InstallScope = InstallScope.global_) -> None:
        teukhos_bin = shutil.which("teukhos") or "teukhos"
        self._write_section(self.config_path(self._effective_scope(scope)), server_name, [
            f"command = {_toml_str(teukhos_bin)}",
            f"args = [{_toml_str('serve')}, {_toml_str(teukhos_config_path)}]",
        ])

    def install_http(self, server_name: str, url: str, api_key: str | None,
                     scope: InstallScope = InstallScope.global_) -> None:
        lines = [f"url = {_toml_str(url)}"]
        if api_key:
            if api_key.startswith("env:"):
                lines.append(f"bearer_token_env_var = {_toml_str(api_key[4:])}")
            else:
                lines.append(f"http_headers = {{ Authorization = {_toml_str('Bearer ' + api_key)} }}")
        self._write_section(self.config_path(self._effective_scope(scope)), server_name, lines)

    def uninstall(self, server_name: str,
                  scope: InstallScope = InstallScope.global_) -> None:
        path = self.config_path(self._effective_scope(scope))
        if path.exists():
            self._write_section(path, server_name, None)

    def _write_section(self, path: Path, server_name: str, lines: list[str] | None) -> None:
        """Replace (or with lines=None, remove) our [mcp_servers.<name>] table, leaving the rest as is."""
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        # A table runs until the next line that starts a header; sub-tables like .headers
        # (written by older versions) go with it.
        pattern = (
            rf"^[ \t]*\[mcp_servers\.{re.escape(_toml_key(server_name))}(?:\.[^\]\n]+)?\][^\n]*\n?"
            r"(?:(?![ \t]*\[).*(?:\n|$))*"
        )
        text = re.sub(pattern, _keep_trailing_comments, text, flags=re.M).rstrip("\n")
        if lines:
            section = "\n".join([f"[mcp_servers.{_toml_key(server_name)}]", *lines])
            text = f"{text}\n\n{section}" if text else section
        text = text + "\n" if text else ""
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"{path} would not be valid TOML ({e}); fix the file by hand and retry") from None
        atomic_write_text(path, text)
