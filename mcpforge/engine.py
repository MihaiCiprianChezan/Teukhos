"""Core engine — transform a ForgeConfig into a running FastMCP server."""

from __future__ import annotations

import inspect
import textwrap
from typing import Any

from fastmcp import FastMCP

from mcpforge.adapters.cli import CLIAdapter
from mcpforge.config import ArgConfig, ArgType, ForgeConfig, OutputConfig, ToolConfig
from mcpforge.output import OutputMapper

# Map YAML arg types to Python types
ARG_TYPE_MAP: dict[ArgType, type] = {
    ArgType.string: str,
    ArgType.integer: int,
    ArgType.number: float,
    ArgType.boolean: bool,
}


def build_server(config: ForgeConfig) -> FastMCP:
    """Build a FastMCP server from a ForgeConfig."""
    mcp = FastMCP(config.forge.name)

    for tool_config in config.tools:
        adapter = _create_adapter(tool_config)
        if adapter is None:
            continue
        handler = _build_handler(tool_config, adapter, tool_config.output)
        mcp.tool(name=tool_config.name, description=tool_config.description)(handler)

    return mcp


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

    # Build parameter list and type annotations for the dynamic function
    params: list[inspect.Parameter] = []
    annotations: dict[str, type] = {}

    for arg in args:
        py_type = ARG_TYPE_MAP.get(arg.type, str)
        default = arg.default if arg.default is not None else (inspect.Parameter.empty if arg.required else None)

        # For boolean args, default to False if no explicit default
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

    # Create the async handler with the correct signature
    async def _handler(**kwargs: Any) -> str:
        result = await adapter.execute(**kwargs)
        if result.exit_code != 0 and output_config.type.value not in ("exit_code",):
            error_msg = result.stderr.strip() or result.stdout.strip()
            if result.exit_code == -1:
                return error_msg  # timeout message
            return f"Error (exit code {result.exit_code}): {error_msg}"
        return mapper.map(result.stdout, result.stderr, result.exit_code)

    # Replace the signature so FastMCP picks up correct parameter schema
    sig = inspect.Signature(parameters=params, return_annotation=str)
    _handler.__signature__ = sig  # type: ignore[attr-defined]
    _handler.__annotations__ = annotations
    _handler.__name__ = tool_config.name
    _handler.__qualname__ = tool_config.name
    _handler.__doc__ = tool_config.description or None

    return _handler
