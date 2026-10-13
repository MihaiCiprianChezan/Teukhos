"""Core engine — transform a ForgeConfig into a running FastMCP server."""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError, ValidationError
from fastmcp.server.auth import AuthProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

from teukhos.adapters.base import AdapterResult
from teukhos.adapters.cli import CLIAdapter
from teukhos.access import auth_check, user_label
from teukhos.audit import AuditLog
from teukhos.auth import build_oauth_provider, resolve_key
from teukhos.config import (
    ARG_TYPE_MAP,
    ArgType,
    AuthMode,
    ForgeConfig,
    OutputConfig,
    OAuthProviderType,
    OutputType,
    ToolConfig,
    TransportType,
)
from teukhos.output import OutputMapper, OutputMappingError


@dataclass
class ServerBundle:
    """Result of building a server — the FastMCP instance + resolved config."""
    mcp: FastMCP
    resolved_auth_keys: list[str] = field(default_factory=list)
    cors_origins: list[str] | None = None


def build_server(config: ForgeConfig, auth: AuthProvider | None = None) -> ServerBundle:
    """Build a FastMCP server from a ForgeConfig.

    In OAuth mode over HTTP the identity provider is attached (`auth` overrides it, for tests).
    """
    oauth = config.auth.oauth if config.auth.mode == AuthMode.oauth else None
    if auth is None and oauth and config.server.transport == TransportType.http:
        auth = build_oauth_provider(oauth, config.server.public_url)

    provider = oauth.provider if oauth else None
    audit = AuditLog(config.server.audit_log) if config.server.audit_log else None
    mcp = FastMCP(
        config.forge.name,
        version=config.forge.version,
        instructions=config.forge.description or None,
        auth=auth,
        middleware=[_AuditRefused(audit, provider)] if audit else None,
    )

    for tool_config in config.tools:
        adapter = _create_adapter(tool_config)
        if adapter is None:
            continue
        handler = _build_handler(tool_config, adapter, tool_config.output, audit, provider)
        mcp.tool(
            name=tool_config.name,
            title=tool_config.title,
            description=tool_config.description,
            annotations=_annotations(tool_config),
            output_schema=None,  # text content only, not a duplicate structuredContent copy
            auth=auth_check([config.auth.allow, tool_config.allow], provider) if oauth else None,
        )(handler)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request: Any) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    # Resolve auth keys (best-effort: missing env vars produce warnings, not crashes)
    resolved_keys: list[str] = []
    if config.auth.mode == AuthMode.api_key and config.auth.api_keys:
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


def _caller(provider: OAuthProviderType | None) -> dict[str, str | None]:
    """Audit fields for the current caller: the identity access rules use, plus the stable subject."""
    token = get_access_token()
    return {"user": user_label(token, provider), "subject": token.subject if token else None}


class _AuditRefused(Middleware):
    """Audit calls that never reach a handler: hidden (not allowed) and unknown tools, and
    arguments refused by schema validation (wrong type, value outside an enum)."""

    def __init__(self, audit: AuditLog, provider: OAuthProviderType | None):
        self.audit = audit
        self.provider = provider

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except (NotFoundError, ValidationError) as e:
            # args are not logged: they may hold secrets, and the name is client-chosen, so cap it
            self.audit.record(**_caller(self.provider), tool=context.message.name[:200], args=None, ok=False,
                              exit_code=None, duration_ms=0,
                              error="unknown tool or not allowed" if isinstance(e, NotFoundError)
                              else "invalid arguments")
            raise


def _annotations(tool_config: ToolConfig) -> ToolAnnotations | None:
    a = tool_config.annotations
    if a is None:
        return None
    return ToolAnnotations(
        read_only_hint=a.read_only,
        destructive_hint=a.destructive,
        idempotent_hint=a.idempotent,
        open_world_hint=a.open_world,
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
    audit: AuditLog | None = None,
    provider: OAuthProviderType | None = None,
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

    secret_names = {a.name for a in args if a.secret}

    def _error(text: str) -> ToolResult:
        # isError lets the client tell a failed call from a result; returning it (rather than
        # raising ToolError) keeps expected tool failures out of the server log
        return ToolResult(content=adapter.redact(text), is_error=True)

    async def _handler(**kwargs: Any) -> str | ToolResult:
        started = time.monotonic()
        result = await adapter.execute(**kwargs)
        response = _respond(result)
        if audit:
            audit.record(
                **_caller(provider),
                tool=tool_config.name,
                args={
                    k: "[REDACTED]" if k in secret_names else (adapter.redact(v) if isinstance(v, str) else v)
                    for k, v in kwargs.items() if v is not None
                },
                ok=not isinstance(response, ToolResult),
                exit_code=None if result.failed else result.exit_code,
                error=result.stderr[:500] if result.failed else None,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
        return response

    def _respond(result: AdapterResult) -> str | ToolResult:
        if result.failed:  # timeout, not found, rejected args
            return _error(result.stderr)
        if result.exit_code != 0 and output_config.type != OutputType.exit_code:
            error_msg = result.stderr.strip() or result.stdout.strip()
            return _error(f"Error (exit code {result.exit_code}): {error_msg}")
        if result.truncated and output_config.type == OutputType.json_field:
            return _error(
                f"Error: output exceeds cli.max_output_bytes ({tool_config.cli.max_output_bytes}); "
                "raise it for this tool to parse the JSON"
            )
        try:
            text = mapper.map(result.stdout, result.stderr, result.exit_code)
        except OutputMappingError as e:
            return _error(str(e))
        # Output was redacted by the adapter; again here because mapping can re-encode values
        return adapter.redact(text)

    sig = inspect.Signature(parameters=params, return_annotation=str)
    _handler.__signature__ = sig  # type: ignore[attr-defined]
    _handler.__annotations__ = annotations
    _handler.__name__ = tool_config.name
    _handler.__qualname__ = tool_config.name
    _handler.__doc__ = tool_config.description or None

    return _handler
