"""Tests for the installer plugin system."""

import json
import tempfile
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
