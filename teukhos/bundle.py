"""Claude Desktop extension (.mcpb): a one-click install of a Teukhos config."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from teukhos import __version__
from teukhos.config import ForgeConfig


def bundle_name(config: ForgeConfig) -> str:
    return re.sub(r"[^a-z0-9]+", "-", config.forge.name.lower()).strip("-") or "teukhos-tools"


def manifest(config: ForgeConfig) -> dict:
    """MCPB manifest 0.4, server type uv: Claude Desktop runs its own uv (mcp_config.command is
    ignored), syncs the bundled pyproject.toml, then starts `teukhos serve` over stdio."""
    secrets = [a for t in config.tools for a in t.args if a.env_default]
    user_config = {
        a.env_default.lower(): {
            "type": "string",
            "title": a.name,
            "description": a.description or f"Value for {a.name}",
            "sensitive": True,  # masked in the UI and kept in the OS keychain
            "required": True,
        }
        for a in secrets
    }
    data = {
        "manifest_version": "0.4",
        "name": bundle_name(config),
        "display_name": config.forge.name,
        "version": config.forge.version,
        "description": config.forge.description or f"{len(config.tools)} CLI tools served by Teukhos",
        "author": {"name": "Teukhos"},
        "server": {
            "type": "uv",
            "entry_point": "teukhos.yaml",
            "mcp_config": {
                "command": "uv",
                "args": ["run", "--directory", "${__dirname}", "teukhos", "serve",
                         "${__dirname}/teukhos.yaml", "--transport", "stdio"],
                "env": {a.env_default: "${user_config." + a.env_default.lower() + "}" for a in secrets},
            },
        },
        "tools": [{"name": t.name, "description": t.description} for t in config.tools],
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"python": ">=3.11"}},
    }
    if user_config:
        data["user_config"] = user_config
    return data


def pyproject(config: ForgeConfig) -> str:
    return (
        "[project]\n"
        f'name = "{bundle_name(config)}"\n'
        f'version = "{config.forge.version}"\n'
        'requires-python = ">=3.11"\n'
        f'dependencies = ["teukhos~={__version__}"]\n'
        "\n[tool.uv]\npackage = false\n"
    )


def build_bundle(config: ForgeConfig, config_path: Path, out: Path) -> Path:
    """Write a .mcpb (a zip with manifest.json at the root) containing the config as-is."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(config), indent=2, ensure_ascii=False) + "\n")
        z.writestr("pyproject.toml", pyproject(config))
        z.writestr("teukhos.yaml", config_path.read_bytes())
    return out
