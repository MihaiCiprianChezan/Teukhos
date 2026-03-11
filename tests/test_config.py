"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest

from mcpforge.config import ForgeConfig, TransportType, load_config


def _write_yaml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def test_load_minimal_config():
    path = _write_yaml("""
forge:
  name: test-server
tools: []
""")
    config = load_config(path)
    assert config.forge.name == "test-server"
    assert config.server.transport == TransportType.stdio
    assert len(config.tools) == 0


def test_load_git_tools():
    config = load_config(Path(__file__).parent.parent / "examples" / "git-tools.yaml")
    assert config.forge.name == "git-tools"
    assert len(config.tools) == 4
    assert config.tools[0].name == "git_log"
    assert config.tools[0].cli is not None
    assert config.tools[0].cli.command == "git"
    assert len(config.tools[0].args) == 1
    assert config.tools[0].args[0].name == "count"


def test_load_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path.yaml")


def test_load_empty_file():
    path = _write_yaml("")
    with pytest.raises(ValueError, match="empty"):
        load_config(path)


def test_config_with_auth():
    path = _write_yaml("""
forge:
  name: auth-server
auth:
  mode: api_key
  api_keys:
    - secret-key-1
    - secret-key-2
tools: []
""")
    config = load_config(path)
    assert config.auth.mode.value == "api_key"
    assert len(config.auth.api_keys) == 2


def test_config_tool_args():
    path = _write_yaml("""
forge:
  name: test
tools:
  - name: test_tool
    description: A test tool
    adapter: cli
    cli:
      command: echo
    args:
      - name: message
        type: string
        required: true
        positional: true
      - name: verbose
        type: boolean
        flag: "--verbose"
""")
    config = load_config(path)
    tool = config.tools[0]
    assert len(tool.args) == 2
    assert tool.args[0].positional is True
    assert tool.args[1].type.value == "boolean"
    assert tool.args[1].flag == "--verbose"
