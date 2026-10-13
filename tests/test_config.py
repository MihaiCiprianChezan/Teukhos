"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest

from teukhos.config import TransportType, load_config


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
    assert len(config.tools) == 5
    # First tool is the ping health check
    assert config.tools[0].name == "ping"
    # Second tool is git_log
    assert config.tools[1].name == "git_log"
    assert config.tools[1].cli is not None
    assert config.tools[1].cli.command == "git"
    assert len(config.tools[1].args) == 1
    assert config.tools[1].args[0].name == "count"


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


from pydantic import ValidationError

from teukhos.config import ArgConfig, CLIAdapterConfig, ForgeConfig


def test_unknown_key_rejected():
    """Typos must fail validation instead of being silently ignored."""
    with pytest.raises(ValidationError, match="working_directory"):
        ForgeConfig.model_validate(
            {"tools": [{"name": "t", "cli": {"command": "x", "working_directory": "/tmp"}}]}
        )
    with pytest.raises(ValidationError, match="secert"):
        ArgConfig.model_validate({"name": "token", "secert": True})


def test_enum_values_coerced_to_arg_type():
    assert ArgConfig(name="n", type="integer", enum=["1", 2]).enum == [1, 2]
    assert ArgConfig(name="s", enum=[1, "a"]).enum == ["1", "a"]


@pytest.mark.parametrize("bad", [
    {"name": "b", "type": "boolean", "enum": ["x"]},
    {"name": "i", "type": "integer", "enum": ["abc"]},
    {"name": "d", "enum": ["a", "b"], "default": "z"},
])
def test_invalid_enum_rejected(bad):
    with pytest.raises(ValidationError, match=f"arg '{bad['name']}'"):
        ArgConfig.model_validate(bad)


def test_max_output_bytes_must_be_positive():
    with pytest.raises(ValidationError):
        CLIAdapterConfig(command="x", max_output_bytes=0)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_load_config_detects_encoding(tmp_path, encoding):
    """Windows editors write BOMs/UTF-16; the locale codec (cp1252) must not be used."""
    path = tmp_path / "teukhos.yaml"
    path.write_text('forge:\n  name: enc\n  description: "— Ё"\ntools: []\n', encoding=encoding)
    config = load_config(path)
    assert config.forge.name == "enc"
    assert config.forge.description == "— Ё"


@pytest.mark.parametrize("bad", [
    {"name": "color", "flag": "--color", "enum": [True, False]},   # YAML on/off
    {"name": "level", "type": "integer", "enum": [1.5, 2]},
])
def test_enum_values_not_silently_changed(bad):
    with pytest.raises(ValidationError):
        ArgConfig.model_validate(bad)


def test_enum_default_coerced_like_values():
    arg = ArgConfig(name="n", type="integer", enum=["1", "2"], default="1")
    assert arg.enum == [1, 2]
    assert arg.default == 1
