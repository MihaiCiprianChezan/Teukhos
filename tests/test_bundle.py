"""Tests for the Claude Desktop .mcpb bundle."""

import json
import tomllib
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from teukhos import __version__
from teukhos.cli import app

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
runner = CliRunner()


def _read(mcpb):
    with zipfile.ZipFile(mcpb) as z:
        return {name: z.read(name) for name in z.namelist()}


def test_bundle_from_example(tmp_path):
    out = tmp_path / "git.mcpb"
    result = runner.invoke(app, ["bundle", str(EXAMPLES_DIR / "git-tools.yaml"), "-o", str(out)])
    assert result.exit_code == 0, result.output
    files = _read(out)
    assert set(files) == {"manifest.json", "pyproject.toml", "teukhos.yaml"}
    assert files["teukhos.yaml"] == (EXAMPLES_DIR / "git-tools.yaml").read_bytes()

    manifest = json.loads(files["manifest.json"])
    assert manifest["manifest_version"] == "0.4" and manifest["name"] == "git-tools"
    assert manifest["server"]["type"] == "uv"
    assert manifest["server"]["mcp_config"]["args"] == [
        "run", "--directory", "${__dirname}", "teukhos", "serve", "${__dirname}/teukhos.yaml",
        "--transport", "stdio",
    ]
    assert {t["name"] for t in manifest["tools"]} >= {"git_log", "git_status"}
    assert "user_config" not in manifest

    project = tomllib.loads(files["pyproject.toml"].decode())
    assert project["project"]["dependencies"] == [f"teukhos~={__version__}"]
    assert project["tool"]["uv"]["package"] is False


def test_env_secret_becomes_sensitive_user_setting(tmp_path):
    config = tmp_path / "teukhos.yaml"
    config.write_text(
        "forge:\n  name: GitHub Tools\n"
        "tools:\n  - name: gh_api\n    cli: {command: gh, subcommand: [api]}\n"
        "    args:\n      - {name: token, flag: --token, secret: true, default: 'env:GH_TOKEN',"
        " description: GitHub token}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["bundle", str(config), "-o", str(tmp_path / "gh.mcpb")])
    assert result.exit_code == 0, result.output
    manifest = json.loads(_read(tmp_path / "gh.mcpb")["manifest.json"])
    assert manifest["name"] == "github-tools"
    assert manifest["user_config"]["gh_token"] == {
        "type": "string", "title": "token", "description": "GitHub token", "sensitive": True, "required": True,
    }
    assert manifest["server"]["mcp_config"]["env"] == {"GH_TOKEN": "${user_config.gh_token}"}
