"""Pydantic models for teukhos.yaml configuration."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator


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


# Map YAML arg types to Python types
ARG_TYPE_MAP: dict[ArgType, type] = {
    ArgType.string: str,
    ArgType.integer: int,
    ArgType.number: float,
    ArgType.boolean: bool,
}


class _Model(BaseModel):
    """Base for all config models: unknown (e.g. misspelled) keys are errors, not silently ignored."""
    model_config = ConfigDict(extra="forbid")


class ForgeInfo(_Model):
    name: str = "teukhos-server"
    version: str = "0.1.0"
    description: str = ""


class ServerConfig(_Model):
    transport: TransportType = TransportType.stdio
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] | None = None


class AuthConfig(_Model):
    mode: AuthMode = AuthMode.none
    api_keys: list[str] = Field(default_factory=list)


class ArgConfig(_Model):
    name: str
    type: ArgType = ArgType.string
    description: str = ""
    required: bool = False
    flag: str | None = None
    default: Any = None
    # Strict members: YAML 1.1 booleans (on/off/yes/no) are an error, not silently 1/0
    enum: list[StrictStr | StrictInt | StrictFloat] | None = None
    positional: bool = False
    secret: bool = False

    @model_validator(mode="after")
    def _check_enum(self) -> ArgConfig:
        """Coerce enum values (and the default) to the arg type so they can be enforced as a Literal."""
        if not self.enum:
            return self
        if self.type == ArgType.boolean:
            raise ValueError(f"arg '{self.name}': enum is not supported for boolean args")
        convert = ARG_TYPE_MAP[self.type]
        try:
            if self.type == ArgType.integer and any(float(v) != int(float(v)) for v in self.enum):
                raise ValueError
            self.enum = [convert(float(v)) if self.type == ArgType.integer else convert(v) for v in self.enum]
            if self.default is not None:
                self.default = convert(self.default)
        except (ValueError, OverflowError):
            raise ValueError(
                f"arg '{self.name}': enum values and default must be valid {self.type.value} values"
            ) from None
        if self.default is not None and self.default not in self.enum:
            raise ValueError(f"arg '{self.name}': default {self.default!r} is not one of {self.enum}")
        return self


class OutputConfig(_Model):
    type: OutputType = OutputType.stdout
    field: str | None = None
    jq: str | None = None
    exit_codes: dict[int, str] | None = None


class CLIAdapterConfig(_Model):
    command: str
    subcommand: list[str] = Field(default_factory=list)
    timeout_seconds: int = 30
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    max_output_bytes: int = Field(default=1_000_000, gt=0)


class ShellAdapterConfig(_Model):
    script: str
    shell: str = "bash"
    timeout_seconds: int = 30
    working_dir: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class ToolAnnotationsConfig(_Model):
    """Behaviour hints clients act on, e.g. auto-approving or running read-only tools in parallel."""
    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None


class ToolConfig(_Model):
    name: str
    title: str | None = None
    description: str = ""
    annotations: ToolAnnotationsConfig | None = None
    adapter: str = "cli"
    cli: CLIAdapterConfig | None = None
    shell: ShellAdapterConfig | None = None
    args: list[ArgConfig] = Field(default_factory=list)
    output: OutputConfig = Field(default_factory=OutputConfig)


class ForgeConfig(_Model):
    forge: ForgeInfo = Field(default_factory=ForgeInfo)
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    tools: list[ToolConfig] = Field(default_factory=list)


def load_config(path: str | Path) -> ForgeConfig:
    """Load and validate a teukhos.yaml configuration file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    # Bytes let PyYAML detect UTF-8, UTF-8 with BOM and UTF-16 instead of using the locale codec
    raw = yaml.safe_load(path.read_bytes())
    if raw is None:
        raise ValueError(f"Config file is empty: {path}")
    return ForgeConfig.model_validate(raw)
