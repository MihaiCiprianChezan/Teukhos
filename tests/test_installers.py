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


def test_claude_desktop_install_http_refused(tmp_path):
    """Claude Desktop skips url entries in its config file, so --url must fail clearly."""
    config_file = tmp_path / "claude_desktop_config.json"
    installer = ClaudeDesktopInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    with pytest.raises(ValueError, match="only supports local"):
        installer.install_http("teukhos-test", "http://localhost:8765/mcp", "literal-key")
    assert not config_file.exists()


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
    from teukhos.installers.cursor import CursorInstaller

    class NoSubstitution(CursorInstaller):
        env_ref = None

    monkeypatch.delenv("TEUKHOS_TEST_UNSET_KEY", raising=False)
    config_file = tmp_path / "mcp.json"
    installer = NoSubstitution()
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
    config_file = tmp_path / ".mcp.json"
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


from teukhos.installers.devin import DevinInstaller


def test_devin_slug_and_windsurf_alias():
    from teukhos.installers import get_installer
    assert DevinInstaller().slug == "devin"
    assert get_installer("windsurf").slug == "devin"


def test_devin_install_stdio(tmp_path):
    config_file = tmp_path / "mcp_config.json"
    installer = DevinInstaller()
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


def _opencode(config_file, monkeypatch):
    import teukhos.installers.base as base_mod
    monkeypatch.setattr(base_mod.shutil, "which", lambda name: "/bin/teukhos")
    installer = OpenCodeInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    return installer


def test_opencode_install_stdio(tmp_path, monkeypatch):
    """OpenCode reads "mcp" with type local and the command as one array (not mcpServers/args)."""
    config_file = tmp_path / "opencode.json"
    config_file.write_text(json.dumps({"$schema": "https://opencode.ai/config.json", "theme": "x"}))
    _opencode(config_file, monkeypatch).install_stdio("teukhos-test", Path("/path/to/config.yaml"))
    data = json.loads(config_file.read_text())
    assert "mcpServers" not in data
    assert data["theme"] == "x"
    assert data["mcp"]["teukhos-test"] == {
        "type": "local",
        "command": ["/bin/teukhos", "serve", str(Path("/path/to/config.yaml"))],
    }


@pytest.mark.parametrize("key, header", [
    ("env:TEUKHOS_API_KEY", "Bearer {env:TEUKHOS_API_KEY}"),
    ("literal-key", "Bearer literal-key"),
])
def test_opencode_install_http(tmp_path, monkeypatch, key, header):
    config_file = tmp_path / "opencode.json"
    _opencode(config_file, monkeypatch).install_http("teukhos-test", "http://h:8765/mcp", key)
    assert json.loads(config_file.read_text())["mcp"]["teukhos-test"] == {
        "type": "remote",
        "url": "http://h:8765/mcp",
        "oauth": False,
        "headers": {"Authorization": header},
    }


def test_opencode_uninstall(tmp_path, monkeypatch):
    config_file = tmp_path / "opencode.json"
    installer = _opencode(config_file, monkeypatch)
    installer.install_stdio("teukhos-a", Path("/a.yaml"))
    installer.install_stdio("teukhos-b", Path("/b.yaml"))
    installer.uninstall("teukhos-a")
    assert set(json.loads(config_file.read_text())["mcp"]) == {"teukhos-b"}


def test_opencode_project_scope(tmp_path):
    config_file = tmp_path / "opencode.json"
    installer = OpenCodeInstaller(cwd=tmp_path)
    installer._config_path_override = {InstallScope.project: config_file}
    installer.install_stdio("teukhos-test", Path("/path/to/config.yaml"), scope=InstallScope.project)
    data = json.loads(config_file.read_text())
    assert data["mcp"]["teukhos-test"]["type"] == "local"


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
    assert len(ALL_INSTALLERS) == 17


def test_get_installer_by_slug():
    inst = get_installer("cursor")
    assert inst is not None
    assert inst.name == "Cursor"


def test_get_installer_unknown():
    assert get_installer("nonexistent") is None


def test_get_all_installers():
    installers = get_all_installers()
    assert len(installers) == 17
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


# ---------------------------------------------------------------------------
# Every client: default config path and the exact entries written
# ---------------------------------------------------------------------------

LINUX_PATHS = {
    # slug: (global path under HOME, project path under CWD or None if global-only)
    "claude-desktop": (".config/Claude/claude_desktop_config.json", None),
    "claude-code": (".claude.json", ".mcp.json"),
    "cursor": (".cursor/mcp.json", ".cursor/mcp.json"),
    "github-copilot": (".config/Code/User/mcp.json", ".vscode/mcp.json"),
    "gemini-cli": (".gemini/settings.json", ".gemini/settings.json"),
    "codex": (".codex/config.toml", ".codex/config.toml"),
    "devin": (".config/devin/mcp_config.json", ".devin/mcp_config.json"),
    "cline": (".cline/data/settings/cline_mcp_settings.json", None),
    "roo-code": (".config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json",
                 ".roo/mcp.json"),
    "continue": (".continue/mcpServers/mcp.json", ".continue/mcpServers/mcp.json"),
    "kiro": (".kiro/settings/mcp.json", ".kiro/settings/mcp.json"),
    "augment": (".augment/settings.json", ".augment/settings.json"),
    "codebuddy": (".codebuddy/.mcp.json", ".mcp.json"),
    "opencode": (".config/opencode/opencode.json", "opencode.json"),
    "trae": (".config/Trae/User/mcp.json", ".trae/mcp.json"),
    "antigravity": (".gemini/config/mcp_config.json", ".agents/mcp_config.json"),
    "lm-studio": (".lmstudio/mcp.json", None),
}

WINDOWS_APPDATA_PATHS = {
    "claude-desktop": "Claude/claude_desktop_config.json",
    "github-copilot": "Code/User/mcp.json",
    "devin": "devin/mcp_config.json",
    "trae": "Trae/User/mcp.json",
}


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    for var in ("XDG_CONFIG_HOME", "CLINE_MCP_SETTINGS_PATH", "CLINE_DATA_DIR", "CLINE_DIR"):
        monkeypatch.delenv(var, raising=False)
    return home


def _set_system(monkeypatch, system):
    import teukhos.installers.base as base_mod
    import teukhos.installers.devin as devin_mod
    monkeypatch.setattr(base_mod.platform, "system", lambda: system)
    monkeypatch.setattr(devin_mod.platform, "system", lambda: system)


def test_every_installer_has_a_path_entry():
    assert set(LINUX_PATHS) == {cls.slug for cls in ALL_INSTALLERS}


@pytest.mark.parametrize("slug", sorted(LINUX_PATHS))
def test_default_paths_linux(fake_home, tmp_path, monkeypatch, slug):
    from teukhos.installers import get_installer
    _set_system(monkeypatch, "Linux")
    cwd = tmp_path / "project"
    installer = get_installer(slug)
    installer.cwd = cwd
    global_rel, project_rel = LINUX_PATHS[slug]
    assert installer.config_path(InstallScope.global_) == fake_home / global_rel
    expected_project = cwd / project_rel if project_rel else fake_home / global_rel
    assert installer.config_path(InstallScope.project) == expected_project


@pytest.mark.parametrize("slug", sorted(WINDOWS_APPDATA_PATHS))
def test_default_paths_windows_appdata(fake_home, tmp_path, monkeypatch, slug):
    from teukhos.installers import get_installer
    _set_system(monkeypatch, "Windows")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert get_installer(slug).config_path(InstallScope.global_) == (
        tmp_path / "roaming" / WINDOWS_APPDATA_PATHS[slug]
    )


def test_cline_path_env_overrides(fake_home, tmp_path, monkeypatch):
    from teukhos.installers.cline import ClineInstaller
    monkeypatch.setenv("CLINE_DIR", str(tmp_path / "c"))
    assert ClineInstaller().config_path(InstallScope.global_) == (
        tmp_path / "c" / "data" / "settings" / "cline_mcp_settings.json"
    )
    monkeypatch.setenv("CLINE_MCP_SETTINGS_PATH", str(tmp_path / "x.json"))
    assert ClineInstaller().config_path(InstallScope.global_) == tmp_path / "x.json"


URL = "http://h:8765/mcp"


def _auth(token):
    return {"headers": {"Authorization": f"Bearer {token}"}}


JSON_ENTRIES = {
    # slug: (extra stdio fields, exact http entry for --key env:TK_TEST_KEY with TK_TEST_KEY=s3cret)
    "claude-code": ({}, {"type": "http", "url": URL, **_auth("${TK_TEST_KEY}")}),
    "cursor": ({"type": "stdio"}, {"url": URL, **_auth("${env:TK_TEST_KEY}")}),
    "github-copilot": ({"type": "stdio"}, {"type": "http", "url": URL, **_auth("${env:TK_TEST_KEY}")}),
    "gemini-cli": ({}, {"url": URL, **_auth("${TK_TEST_KEY}")}),
    "devin": ({}, {"url": URL, **_auth("${env:TK_TEST_KEY}")}),
    "cline": ({}, {"type": "streamableHttp", "url": URL, **_auth("${env:TK_TEST_KEY}")}),
    "roo-code": ({}, {"type": "streamable-http", "url": URL, **_auth("${env:TK_TEST_KEY}")}),
    "continue": ({}, {"url": URL, **_auth("s3cret")}),
    "kiro": ({}, {"url": URL, **_auth("${TK_TEST_KEY}")}),
    "augment": ({}, {"url": URL, **_auth("s3cret")}),
    "codebuddy": ({"type": "stdio"}, {"type": "http", "url": URL, **_auth("${TK_TEST_KEY}")}),
    "trae": ({}, {"url": URL, **_auth("s3cret")}),
    "antigravity": ({}, {"serverUrl": URL, **_auth("s3cret")}),
    "lm-studio": ({}, {"url": URL, **_auth("s3cret")}),
}


@pytest.mark.parametrize("slug", sorted(JSON_ENTRIES))
def test_json_installer_entries(tmp_path, monkeypatch, slug):
    import teukhos.installers.base as base_mod
    from teukhos.installers import get_installer
    monkeypatch.setattr(base_mod.shutil, "which", lambda name: "/bin/teukhos")
    monkeypatch.setenv("TK_TEST_KEY", "s3cret")
    installer = get_installer(slug)
    config_file = tmp_path / "config.json"
    installer._config_path_override = {InstallScope.global_: config_file}
    stdio_extra, http_entry = JSON_ENTRIES[slug]

    installer.install_stdio("teukhos-a", Path("/x.yaml"))
    installer.install_http("teukhos-b", URL, "env:TK_TEST_KEY")
    servers = json.loads(config_file.read_text())[installer.config_key]
    assert servers["teukhos-a"] == {"command": "/bin/teukhos", "args": ["serve", str(Path("/x.yaml"))], **stdio_extra}
    assert servers["teukhos-b"] == http_entry


def test_gemini_allowlists_key_env_var(tmp_path, monkeypatch):
    """Gemini drops env vars named like *KEY* from header expansion unless allowlisted."""
    from teukhos.installers.gemini_cli import GeminiCLIInstaller
    config_file = tmp_path / "settings.json"
    installer = GeminiCLIInstaller()
    installer._config_path_override = {InstallScope.global_: config_file}
    installer.install_http("teukhos-a", URL, "env:TEUKHOS_API_KEY")
    installer.install_http("teukhos-b", URL, "env:TEUKHOS_API_KEY")
    data = json.loads(config_file.read_text())
    assert data["security"]["environmentVariableRedaction"]["allowed"] == ["TEUKHOS_API_KEY"]


def test_dest_installer_formats(tmp_path, monkeypatch):
    import teukhos.installers.base as base_mod
    from teukhos.installers.base import DestInstaller
    monkeypatch.setattr(base_mod.shutil, "which", lambda name: "/bin/teukhos")
    vscode = DestInstaller(tmp_path / "a.json", "servers")
    vscode.install_http("teukhos-a", URL, "env:K")
    assert json.loads((tmp_path / "a.json").read_text())["servers"]["teukhos-a"] == {
        "type": "http", "url": URL, **_auth("${env:K}")}  # VS Code sends a bare ${K} literally
    generic = DestInstaller(tmp_path / "b.json")
    generic.install_stdio("teukhos-a", Path("/x.yaml"))
    assert json.loads((tmp_path / "b.json").read_text())["mcpServers"]["teukhos-a"] == {
        "command": "/bin/teukhos", "args": ["serve", str(Path("/x.yaml"))]}


def test_lm_studio_home_pointer_file(fake_home, tmp_path):
    from teukhos.installers.lm_studio import LMStudioInstaller
    fake_home.mkdir(parents=True)
    (fake_home / ".lmstudio-home-pointer").write_text(str(tmp_path / "models-drive" / "lmstudio") + "\n")
    assert LMStudioInstaller().config_path(InstallScope.global_) == tmp_path / "models-drive" / "lmstudio" / "mcp.json"


def test_opencode_oauth_server_entry_lets_opencode_log_in(tmp_path, monkeypatch):
    config_file = tmp_path / "opencode.json"
    _opencode(config_file, monkeypatch).install_http("teukhos-test", URL, "")
    assert json.loads(config_file.read_text())["mcp"]["teukhos-test"] == {"type": "remote", "url": URL}


def test_continue_detected_by_its_home_folder(fake_home):
    from teukhos.installers.continue_dev import ContinueDevInstaller
    assert not ContinueDevInstaller().detect()
    (fake_home / ".continue").mkdir(parents=True)
    assert ContinueDevInstaller().detect()
