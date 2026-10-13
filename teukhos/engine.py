"""Core engine — transform a ForgeConfig into a running FastMCP server."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Literal

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from teukhos.adapters.cli import CLIAdapter
from teukhos.config import ARG_TYPE_MAP, ArgType, AuthMode, ForgeConfig, OutputConfig, OutputType, ToolConfig
from teukhos.output import OutputMapper


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
        # output_schema=None: return text content only, not a duplicate structuredContent copy
        mcp.tool(name=tool_config.name, description=tool_config.description, output_schema=None)(handler)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request: Any) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Resolve auth keys (best-effort: missing env vars produce warnings, not crashes)
    resolved_keys: list[str] = []
    if config.auth.mode == AuthMode.api_key and config.auth.api_keys:
        import logging

        from teukhos.auth import resolve_key

        logger = logging.getLogger("teukhos")
        for raw_key in config.auth.api_keys:
            try:
                resolved_keys.append(resolve_key(raw_key))
            except ValueError as e:
                logger.warning("Auth key resolution skipped: %s", e)

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
    annotations: dict[str, Any] = {}

    for arg in args:
        if arg.secret and arg.default is not None:
            continue  # operator-held: not exposed; the adapter injects and redacts it
        py_type = Literal[tuple(arg.enum)] if arg.enum else ARG_TYPE_MAP.get(arg.type, str)
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
        if result.failed:  # timeout, not found, rejected args
            return result.stderr
        if result.exit_code != 0 and output_config.type != OutputType.exit_code:
            error_msg = result.stderr.strip() or result.stdout.strip()
            return f"Error (exit code {result.exit_code}): {error_msg}"
        if result.truncated and output_config.type == OutputType.json_field:
            return (
                f"Error: output exceeds cli.max_output_bytes ({tool_config.cli.max_output_bytes}); "
                "raise it for this tool to parse the JSON"
            )
        # Output was redacted by the adapter; again here because mapping can re-encode values
        return adapter.redact(mapper.map(result.stdout, result.stderr, result.exit_code))

    sig = inspect.Signature(parameters=params, return_annotation=str)
    _handler.__signature__ = sig  # type: ignore[attr-defined]
    _handler.__annotations__ = annotations
    _handler.__name__ = tool_config.name
    _handler.__qualname__ = tool_config.name
    _handler.__doc__ = tool_config.description or None

    return _handler
