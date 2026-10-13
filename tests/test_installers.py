"""Tests for the installer plugin system."""

import json
import stat
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

from teukhos.installers.base import (
    BaseInstaller,
    InstallScope,
    atomic_write_json,
    merge_mcp_entry,
    read_json_config,
    remove_mcp_entry,
)


def test_install_scope_values():
    assert InstallScope.global_.value == "global"
    assert InstallScope.project.value == "project"


def test_read_json_config_existing():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"mcpServers": {"existing": {}}}, f)
        path = Path(f.name)
    result = read_json_config(path)
    assert result == {"mcpServers": {"existing": {}}}


def test_read_json_config_missing():
    result = read_json_config(Path("/nonexistent/config.json"))
    assert result == {}


def test_read_json_config_malformed():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json")
        path = Path(f.name)
    with pytest.raises(json.JSONDecodeError):
        read_json_config(path)


def test_atomic_write_json(tmp_path):
    target = tmp_path / "subdir" / "config.json"
    data = {"mcpServers": {"test": {"command": "echo"}}}
    atomic_write_json(target, data)
    assert target.exists()
    assert json.loads(target.read_text()) == data


def test_atomic_write_json_creates_backup(tmp_path):
    target = tmp_path / "config.json"
    target.write_text(json.dumps({"old": True}))
    atomic_write_json(target, {"new": True})
    backup = tmp_path / "config.json.teukhos-backup"
    assert backup.exists()
    assert json.loads(backup.read_text()) == {"old": True}


def test_merge_mcp_entry():
    existing = {"mcpServers": {"other-server": {"command": "other"}}}
    entry = {"command": "teukhos", "args": ["serve", "config.yaml"]}
    result = merge_mcp_entry(existing, "teukhos-test", entry, key="mcpServers")
    assert result["mcpServers"]["teukhos-test"] == entry
    assert result["mcpServers"]["other-server"] == {"command": "other"}


def test_merge_mcp_entry_creates_key():
    existing = {}
    entry = {"command": "teukhos"}
    result = merge_mcp_entry(existing, "teukhos-test", entry, key="mcpServers")
    assert result == {"mcpServers": {"teukhos-test": {"command": "teukhos"}}}


def test_remove_mcp_entry():
    config = {"mcpServers": {"a": {}, "b": {}}}
    result = remove_mcp_entry(config, "a")
    assert "a" not in result["mcpServers"]
    assert "b" in result["mcpServers"]


def test_base_installer_is_abstract():
    with pytest.raises(TypeError):
        BaseInstaller()


from teukhos.installers.claude_desktop import ClaudeDesktopInstaller


def test_claude_desktop_slug():
    installer = ClaudeDesktopInstaller()
    assert installer.slug == "claude-desktop"
    assert installer.name == "Claude Desktop"


def test_claude_desktop_no_project_scope():
    installer = ClaudeDesktopInstaller()
    assert InstallScope.project not in installer.supported_scopes


def test_claude_desktop_install_stdio(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]
    assert data["mcpServers"]["teukhos-test"]["args"] == ["serve", str(Path("/path/to/config.yaml"))]


def test_claude_desktop_install_http(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_http("teukhos-test", "http://localhost:8765/mcp", "literal-key")
    data = json.loads(config_file.read_text())
    entry = data["mcpServers"]["teukhos-test"]
    assert entry["url"] == "http://localhost:8765/mcp"
    assert entry["headers"]["Authorization"] == "Bearer literal-key"


def test_claude_desktop_uninstall(tmp_path):
    config_file = tmp_path / "claude_desktop_config.json"
    config_file.write_text(json.dumps({
        "mcpServers": {"teukhos-test": {"command": "teukhos"}, "other": {"command": "other"}}
    }))
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.uninstall("teukhos-test")
    data = json.loads(config_file.read_text())
    assert "teukhos-test" not in data["mcpServers"]
    assert "other" in data["mcpServers"]


def test_json_uninstall_missing_config_is_noop(tmp_path):
    """Uninstall must not create a config (which would make the client look installed)."""
    config_file = tmp_path / "Claude" / "claude_desktop_config.json"
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.uninstall("teukhos-test")
    assert not config_file.parent.exists()


def test_json_install_http_unresolved_env_key_raises(tmp_path, monkeypatch):
    """Clients without ${VAR} support must not get a literal 'Bearer env:VAR' header."""
    monkeypatch.delenv("TEUKHOS_TEST_UNSET_KEY", raising=False)
    config_file = tmp_path / "claude_desktop_config.json"
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    with pytest.raises(ValueError, match="TEUKHOS_TEST_UNSET_KEY"):
        installer.install_http("teukhos-test", "http://h/mcp", "env:TEUKHOS_TEST_UNSET_KEY")
    assert not config_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_atomic_write_json_keeps_symlink(tmp_path):
    real = tmp_path / "dotfiles" / "mcp.json"
    real.parent.mkdir()
    real.write_text("{}")
    link = tmp_path / "mcp.json"
    link.symlink_to(real)
    atomic_write_json(link, {"a": 1})
    assert link.is_symlink()
    assert json.loads(real.read_text()) == {"a": 1}


from teukhos.installers.claude_code import ClaudeCodeInstaller


def test_claude_code_slug():
    installer = ClaudeCodeInstaller()
    assert installer.slug == "claude-code"
    assert InstallScope.project in installer.supported_scopes


def test_claude_code_install_stdio(tmp_path):
    config_file = tmp_path / ".claude.json"
    installer = ClaudeCodeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


def test_claude_code_install_http_env_substitution(tmp_path):
    config_file = tmp_path / ".claude.json"
    installer = ClaudeCodeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_http("teukhos-test", "http://host:8765/mcp", "env:TEUKHOS_API_KEY")
    data = json.loads(config_file.read_text())
    entry = data["mcpServers"]["teukhos-test"]
    assert entry["url"] == "http://host:8765/mcp"
    assert "${TEUKHOS_API_KEY}" in entry["headers"]["Authorization"]


def test_claude_code_project_scope(tmp_path):
    config_file = tmp_path / ".claude" / "settings.json"
    installer = ClaudeCodeInstaller(cwd=tmp_path)
    installer._config_path_override = {InstallScope.project: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"), scope=InstallScope.project)
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.cursor import CursorInstaller


def test_cursor_slug():
    installer = CursorInstaller()
    assert installer.slug == "cursor"
    assert InstallScope.project in installer.supported_scopes


def test_cursor_install_stdio(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = CursorInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.github_copilot import GitHubCopilotInstaller


def test_github_copilot_slug():
    installer = GitHubCopilotInstaller()
    assert installer.slug == "github-copilot"


def test_github_copilot_uses_servers_key(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = GitHubCopilotInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "servers" in data
    entry = data["servers"]["teukhos-test"]
    assert entry["type"] == "stdio"


def test_github_copilot_http_has_type(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = GitHubCopilotInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_http("teukhos-test", "http://host:8765/mcp", None)
    data = json.loads(config_file.read_text())
    entry = data["servers"]["teukhos-test"]
    assert entry["type"] == "http"
    assert entry["url"] == "http://host:8765/mcp"


from teukhos.installers.gemini_cli import GeminiCLIInstaller
from teukhos.installers.codex import CodexInstaller


def test_gemini_cli_slug():
    installer = GeminiCLIInstaller()
    assert installer.slug == "gemini-cli"
    assert InstallScope.project in installer.supported_scopes


def test_gemini_cli_install_stdio(tmp_path):
    config_file = tmp_path / "settings.json"
    installer = GeminiCLIInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


def test_codex_slug():
    installer = CodexInstaller()
    assert installer.slug == "codex"
    assert InstallScope.project in installer.supported_scopes


def _codex(config_file, monkeypatch, teukhos_bin=r"C:\Python\Scripts\teukhos.EXE"):
    import teukhos.installers.codex as codex_mod
    monkeypatch.setattr(codex_mod.shutil, "which", lambda name: teukhos_bin)
    installer = CodexInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    return installer


def _servers(config_file):
    return tomllib.loads(config_file.read_text(encoding="utf-8"))["mcp_servers"]


def test_codex_install_stdio(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    _codex(config_file, monkeypatch).install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    assert "[mcp_servers.teukhos-test]" in config_file.read_text()
    assert _servers(config_file)["teukhos-test"] == {
        "command": r"C:\Python\Scripts\teukhos.EXE",
        "args": ["serve", str(Path("/path/to/config.yaml"))],
    }


def test_codex_windows_paths_round_trip(tmp_path, monkeypatch):
    """Backslashes must be escaped: in a TOML string \\U and \\t are escape sequences."""
    config_file = tmp_path / "config.toml"
    config_path = r"C:\Users\x\tools\new\teukhos.yaml"
    _codex(config_file, monkeypatch).install_stdio("teukhos-test", config_path)
    entry = _servers(config_file)["teukhos-test"]
    assert entry["command"] == r"C:\Python\Scripts\teukhos.EXE"
    assert entry["args"] == ["serve", config_path]


def test_codex_install_http(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    _codex(config_file, monkeypatch).install_http("teukhos-test", "http://host:8765/mcp", None)
    assert _servers(config_file)["teukhos-test"] == {"url": "http://host:8765/mcp"}


def test_codex_install_http_with_env_api_key(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    _codex(config_file, monkeypatch).install_http("teukhos-test", "http://host:8765/mcp", "env:TEUKHOS_API_KEY")
    assert _servers(config_file)["teukhos-test"] == {
        "url": "http://host:8765/mcp",
        "bearer_token_env_var": "TEUKHOS_API_KEY",
    }


def test_codex_install_http_with_literal_api_key(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    _codex(config_file, monkeypatch).install_http("teukhos-test", "http://host:8765/mcp", 'k"ey\\1')
    entry = _servers(config_file)["teukhos-test"]
    assert entry["http_headers"] == {"Authorization": 'Bearer k"ey\\1'}


def test_codex_uninstall(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    installer = _codex(config_file, monkeypatch)
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    installer.install_stdio("other-server", Path("/path/to/other.yaml"))
    installer.uninstall("teukhos-test")
    assert set(_servers(config_file)) == {"other-server"}


def test_codex_reinstall_and_uninstall_preserve_user_config(tmp_path, monkeypatch):
    """Reinstalling must not leave `args = [...]` debris; uninstall restores the original."""
    config_file = tmp_path / "config.toml"
    original = (
        '# my codex config\n'
        'model = "o4"\n'
        'notes = """line1\n\n\n\nline2"""\n'
        '\n'
        '[mcp_servers.context7]\n'
        'command = "npx"\n'
        'args = ["-y", "@upstash/context7-mcp"]\n'
    )
    config_file.write_text(original, encoding="utf-8")
    installer = _codex(config_file, monkeypatch)
    for _ in range(3):
        installer.install_stdio("teukhos-a", Path("/a.yaml"))
    installer.install_http("teukhos-b", "http://h/mcp", "env:K")
    installer.install_http("teukhos-b", "http://h2/mcp", "env:K")
    servers = _servers(config_file)
    assert set(servers) == {"context7", "teukhos-a", "teukhos-b"}
    assert servers["context7"] == {"command": "npx", "args": ["-y", "@upstash/context7-mcp"]}
    assert servers["teukhos-b"]["url"] == "http://h2/mcp"
    installer.uninstall("teukhos-a")
    installer.uninstall("teukhos-b")
    assert tomllib.loads(config_file.read_text(encoding="utf-8")) == tomllib.loads(original)
    assert "# my codex config" in config_file.read_text(encoding="utf-8")


def test_codex_server_name_cannot_inject_tables(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    name = 'teukhos-x]\ncommand = "teukhos"\n[mcp_servers.evil]\ncommand = "/bin/sh'
    installer = _codex(config_file, monkeypatch)
    installer.install_stdio(name, Path("/a.yaml"))
    assert set(_servers(config_file)) == {name}
    installer.uninstall(name)
    assert config_file.read_text() == ""


@pytest.mark.parametrize("name", ["teukhos-python3.12", "teukhos-git tools", "teukhos-ünï"])
def test_codex_unusual_names_round_trip(tmp_path, monkeypatch, name):
    config_file = tmp_path / "config.toml"
    installer = _codex(config_file, monkeypatch)
    installer.install_stdio("teukhos-python3", Path("/other.yaml"))
    installer.install_stdio(name, Path("/a.yaml"))
    installer.install_stdio(name, Path("/b.yaml"))
    assert _servers(config_file)[name]["args"] == ["serve", str(Path("/b.yaml"))]
    installer.uninstall(name)
    assert set(_servers(config_file)) == {"teukhos-python3"}


def test_codex_repairs_config_broken_by_old_versions(tmp_path, monkeypatch):
    """Older versions wrote unescaped Windows paths (invalid TOML); reinstall must fix it."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'model = "o4"\n\n'
        '[mcp_servers.teukhos-x]\n'
        'type = "stdio"\n'
        'command = "C:\\Python\\Scripts\\teukhos.EXE"\n'
        'args = ["serve", "C:\\Users\\x\\teukhos.yaml"]\n',
        encoding="utf-8",
    )
    _codex(config_file, monkeypatch).install_stdio("teukhos-x", r"C:\Users\x\teukhos.yaml")
    data = tomllib.loads(config_file.read_text(encoding="utf-8"))
    assert data["model"] == "o4"
    assert data["mcp_servers"]["teukhos-x"]["args"] == ["serve", r"C:\Users\x\teukhos.yaml"]


def test_codex_refuses_to_write_invalid_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    broken = '[mcp_servers.other]\ncommand = "a"\ncommand = "b"\n'
    config_file.write_text(broken, encoding="utf-8")
    with pytest.raises(ValueError, match="not be valid TOML"):
        _codex(config_file, monkeypatch).install_stdio("teukhos-x", Path("/a.yaml"))
    assert config_file.read_text(encoding="utf-8") == broken


def test_codex_uninstall_missing_file_is_noop(tmp_path, monkeypatch):
    config_file = tmp_path / "missing" / "config.toml"
    _codex(config_file, monkeypatch).uninstall("teukhos-x")
    assert not config_file.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_codex_new_config_is_private(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    _codex(config_file, monkeypatch).install_http("teukhos-x", "http://h/mcp", "literal-key")
    assert stat.S_IMODE(config_file.stat().st_mode) == 0o600


def test_codex_project_scope(tmp_path, monkeypatch):
    config_file = tmp_path / ".codex" / "config.toml"
    import teukhos.installers.codex as codex_mod
    monkeypatch.setattr(codex_mod.shutil, "which", lambda name: None)
    installer = CodexInstaller(cwd=tmp_path)
    installer._config_path_override = {InstallScope.project: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"), scope=InstallScope.project)
    assert _servers(config_file)["teukhos-test"]["command"] == "teukhos"


from teukhos.installers.windsurf import WindsurfInstaller


def test_windsurf_slug():
    installer = WindsurfInstaller()
    assert installer.slug == "windsurf"
    assert installer.name == "Windsurf"


def test_windsurf_install_stdio(tmp_path):
    config_file = tmp_path / "mcp_config.json"
    installer = WindsurfInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.roo_code import RooCodeInstaller


def test_roo_code_slug():
    installer = RooCodeInstaller()
    assert installer.slug == "roo-code"
    assert installer.name == "Roo Code"


def test_roo_code_install_stdio(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = RooCodeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.continue_dev import ContinueDevInstaller


def test_continue_dev_slug():
    installer = ContinueDevInstaller()
    assert installer.slug == "continue"
    assert installer.name == "Continue.dev"


def test_continue_dev_install_stdio(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = ContinueDevInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.kiro import KiroInstaller


def test_kiro_slug():
    installer = KiroInstaller()
    assert installer.slug == "kiro"
    assert installer.name == "Kiro"


def test_kiro_install_stdio(tmp_path):
    config_file = tmp_path / "settings.json"
    installer = KiroInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.auggie import AuggieInstaller


def test_auggie_slug():
    installer = AuggieInstaller()
    assert installer.slug == "augment"
    assert installer.name == "Augment Code"


def test_auggie_install_stdio(tmp_path):
    config_file = tmp_path / "settings.json"
    installer = AuggieInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.codebuddy import CodeBuddyInstaller


def test_codebuddy_slug():
    installer = CodeBuddyInstaller()
    assert installer.slug == "codebuddy"
    assert installer.name == "CodeBuddy"


def test_codebuddy_install_stdio(tmp_path):
    config_file = tmp_path / ".mcp.json"
    installer = CodeBuddyInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]
    assert data["mcpServers"]["teukhos-test"]["type"] == "stdio"


def test_codebuddy_project_scope(tmp_path):
    config_file = tmp_path / ".mcp.json"
    installer = CodeBuddyInstaller(cwd=tmp_path)
    installer._config_path_override = {InstallScope.project: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"), scope=InstallScope.project)
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.opencode import OpenCodeInstaller


def test_opencode_slug():
    installer = OpenCodeInstaller()
    assert installer.slug == "opencode"
    assert installer.name == "OpenCode"


def test_opencode_install_stdio(tmp_path):
    config_file = tmp_path / "opencode.json"
    installer = OpenCodeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


def test_opencode_project_scope(tmp_path):
    config_file = tmp_path / "opencode.json"
    installer = OpenCodeInstaller(cwd=tmp_path)
    installer._config_path_override = {InstallScope.project: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"), scope=InstallScope.project)
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.trae import TraeInstaller


def test_trae_slug():
    installer = TraeInstaller()
    assert installer.slug == "trae"
    assert installer.name == "Trae"


def test_trae_install_stdio(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = TraeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


from teukhos.installers.cline import ClineInstaller


def test_cline_slug():
    installer = ClineInstaller()
    assert installer.slug == "cline"
    assert installer.name == "Cline"


def test_cline_install_stdio(tmp_path):
    config_file = tmp_path / "mcp.json"
    installer = ClineInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "teukhos-test" in data["mcpServers"]


# --- Registry tests ---

from teukhos.installers import (
    ALL_INSTALLERS,
    discover_clients,
    get_all_installers,
    get_installer,
)


def test_all_installers_have_unique_slugs():
    slugs = [cls.slug for cls in ALL_INSTALLERS]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"


def test_all_installers_count():
    assert len(ALL_INSTALLERS) == 15


def test_get_installer_by_slug():
    inst = get_installer("cursor")
    assert inst is not None
    assert inst.name == "Cursor"


def test_get_installer_unknown():
    assert get_installer("nonexistent") is None


def test_get_all_installers():
    installers = get_all_installers()
    assert len(installers) == 15
    assert all(isinstance(i, BaseInstaller) for i in installers)


def test_discover_clients_returns_list():
    """discover_clients should return a list (may be empty in test env)."""
    result = discover_clients()
    assert isinstance(result, list)


def test_codex_uninstall_keeps_comments_of_next_table(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    installer = _codex(config_file, monkeypatch)
    installer.install_stdio("teukhos-x", Path("/a.yaml"))
    with open(config_file, "a", encoding="utf-8") as f:
        f.write('\n# GitHub MCP: token lives in GH_TOKEN\n[mcp_servers.github]\ncommand = "gh-mcp"\n')
    installer.uninstall("teukhos-x")
    text = config_file.read_text(encoding="utf-8")
    assert "# GitHub MCP: token lives in GH_TOKEN" in text
    assert set(_servers(config_file)) == {"github"}


def test_codex_removes_table_with_inner_comment(tmp_path, monkeypatch):
    config_file = tmp_path / "config.toml"
    config_file.write_text('[mcp_servers.teukhos-x]\n# note\ncommand = "a"\nargs = ["b"]\n', encoding="utf-8")
    _codex(config_file, monkeypatch).uninstall("teukhos-x")
    assert tomllib.loads(config_file.read_text(encoding="utf-8")) == {}


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_atomic_write_json_replaces_dangling_symlink(tmp_path):
    """A planted link to a missing file must not create that file elsewhere."""
    outside = tmp_path / "outside" / "nested" / "mcp.json"
    link = tmp_path / "project" / ".cursor" / "mcp.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    atomic_write_json(link, {"a": 1})
    assert not link.is_symlink()
    assert not outside.parent.exists()
