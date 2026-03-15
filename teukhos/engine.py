"""Core engine — transform a ForgeConfig into a running FastMCP server."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from fastmcp import FastMCP

from teukhos.adapters.cli import CLIAdapter
from teukhos.config import ArgConfig, ArgType, AuthMode, ForgeConfig, OutputConfig, ToolConfig
from teukhos.output import OutputMapper

# Map YAML arg types to Python types
ARG_TYPE_MAP: dict[ArgType, type] = {
    ArgType.string: str,
    ArgType.integer: int,
    ArgType.number: float,
    ArgType.boolean: bool,
}


@dataclass
class ServerBundle:
    """Result of building a server — the FastMCP instance + resolved config."""
    mcp: FastMCP
    resolved_auth_keys: list[str] = field(default_factory=list)
    cors_origins: list[str] | None = None


def build_server(config: ForgeConfig) -> ServerBundle:
    """Build a FastMCP server from a ForgeConfig."""
    mcp = FastMCP(config.forge.name)

    for tool_config in config.tools:
        adapter = _create_adapter(tool_config)
        if adapter is None:
            continue
        handler = _build_handler(tool_config, adapter, tool_config.output)
        mcp.tool(name=tool_config.name, description=tool_config.description)(handler)

    # Resolve auth keys
    resolved_keys: list[str] = []
    if config.auth.mode == AuthMode.api_key and config.auth.api_keys:
        from teukhos.auth import resolve_key
        resolved_keys = [resolve_key(k) for k in config.auth.api_keys]

    return ServerBundle(
        mcp=mcp,
        resolved_auth_keys=resolved_keys,
        cors_origins=config.server.cors_origins,
    )


def _create_adapter(tool_config: ToolConfig) -> CLIAdapter | None:
    """Create the appropriate adapter for a tool."""
    if tool_config.adapter == "cli":
        if tool_config.cli is None:
            return None
        return CLIAdapter(tool_config.cli, tool_config.args)
    return None


def _build_handler(
    tool_config: ToolConfig,
    adapter: CLIAdapter,
    output_config: OutputConfig,
) -> Any:
    """Dynamically build an async handler function with typed parameters.

    FastMCP infers JSON schema from function signatures, so we create a real
    function with proper parameter annotations at runtime.
    """
    mapper = OutputMapper(output_config)
    args = tool_config.args

    params: list[inspect.Parameter] = []
    annotations: dict[str, type] = {}

    for arg in args:
        py_type = ARG_TYPE_MAP.get(arg.type, str)
        default = arg.default if arg.default is not None else (
            inspect.Parameter.empty if arg.required else None
        )

        if arg.type == ArgType.boolean and default is None:
            default = False

        param = inspect.Parameter(
            name=arg.name,
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=default,
            annotation=py_type if arg.required else py_type | None,
        )
        params.append(param)
        annotations[arg.name] = py_type if arg.required else py_type | None

    annotations["return"] = str

    async def _handler(**kwargs: Any) -> str:
        result = await adapter.execute(**kwargs)
        if result.exit_code != 0 and output_config.type.value not in ("exit_code",):
            error_msg = result.stderr.strip() or result.stdout.strip()
            if result.exit_code == -1:
                return error_msg
            return f"Error (exit code {result.exit_code}): {error_msg}"
        return mapper.map(result.stdout, result.stderr, result.exit_code)

    sig = inspect.Signature(parameters=params, return_annotation=str)
    _handler.__signature__ = sig  # type: ignore[attr-defined]
    _handler.__annotations__ = annotations
    _handler.__name__ = tool_config.name
    _handler.__qualname__ = tool_config.name
    _handler.__doc__ = tool_config.description or None

    return _handler
