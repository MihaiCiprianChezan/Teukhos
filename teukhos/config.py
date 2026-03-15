"""Pydantic models for teukhos.yaml configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class TransportType(str, Enum):
    stdio = "stdio"
    http = "http"


class AuthMode(str, Enum):
    none = "none"
    api_key = "api_key"


class OutputType(str, Enum):
    stdout = "stdout"
    json_field = "json_field"
    exit_code = "exit_code"
    stderr = "stderr"


class ArgType(str, Enum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"


class ForgeInfo(BaseModel):
    name: str = "teukhos-server"
    version: str = "0.1.0"
    description: str = ""


class ServerConfig(BaseModel):
    transport: TransportType = TransportType.stdio
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] | None = None


class AuthConfig(BaseModel):
    mode: AuthMode = AuthMode.none
    api_keys: list[str] = Field(default_factory=list)


class ArgConfig(BaseModel):
    name: str
    type: ArgType = ArgType.string
    description: str = ""
    required: bool = False
    flag: str | None = None
    default: Any = None
    enum: list[str] | None = None
    positional: bool = False
    secret: bool = False


class OutputConfig(BaseModel):
    type: OutputType = OutputType.stdout
    field: str | None = None
    jq: str | None = None
    exit_codes: dict[int, str] | None = None


class CLIAdapterConfig(BaseModel):
    command: str
    subcommand: list[str] = Field(default_factory=list)
    timeout_seconds: int = 30
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class ShellAdapterConfig(BaseModel):
    script: str
    shell: str = "bash"
    timeout_seconds: int = 30
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class ToolConfig(BaseModel):
    name: str
    description: str = ""
    adapter: str = "cli"
    cli: CLIAdapterConfig | None = None
    shell: ShellAdapterConfig | None = None
    args: list[ArgConfig] = Field(default_factory=list)
    output: OutputConfig = Field(default_factory=OutputConfig)


class ForgeConfig(BaseModel):
    forge: ForgeInfo = Field(default_factory=ForgeInfo)
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    tools: list[ToolConfig] = Field(default_factory=list)


def load_config(path: str | Path) -> ForgeConfig:
    """Load and validate a teukhos.yaml configuration file.

    Also accepts legacy mcp-forge.yaml filenames for backward compatibility.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raise ValueError(f"Config file is empty: {path}")
    return ForgeConfig.model_validate(raw)
