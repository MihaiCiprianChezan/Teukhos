"""Pydantic models for teukhos.yaml configuration."""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator


class TransportType(str, Enum):
    stdio = "stdio"
    http = "http"


class AuthMode(str, Enum):
    none = "none"
    api_key = "api_key"
    oauth = "oauth"


class OAuthProviderType(str, Enum):
    entra = "entra"    # Microsoft Entra ID (Azure AD)
    google = "google"  # Google accounts / Workspace
    github = "github"
    oidc = "oidc"      # any OpenID Connect provider: Okta, Keycloak, Auth0, ...


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


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class ServerConfig(_Model):
    transport: TransportType = TransportType.stdio
    host: str = "127.0.0.1"
    port: int = 8765
    cors_origins: list[str] | None = None
    audit_log: str | None = None  # JSONL file: one line per tool call (who, tool, args, outcome)
    # Public origin clients reach this server at (https://tools.example.com); they use <public_url>/mcp
    public_url: str | None = None
    # Plain JSON responses instead of SSE streams, for proxies without SSE (Cloudflare quick tunnels)
    json_response: bool = False

    @model_validator(mode="after")
    def _check_public_url(self) -> ServerConfig:
        if self.public_url is None:
            return self
        url = urlparse(self.public_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.path not in ("", "/"):
            raise ValueError("server.public_url must be an origin like https://tools.example.com (no path)")
        if url.scheme == "http" and url.hostname not in LOOPBACK_HOSTS:
            raise ValueError("server.public_url must use https (plain http is allowed only for localhost)")
        self.public_url = self.public_url.rstrip("/")
        return self


class AccessRule(_Model):
    """Who may use a server or tool (OAuth mode). Any match allows; all lists empty allows nobody."""
    emails: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)   # email domain; Google Workspace 'hd'
    groups: list[str] = Field(default_factory=list)    # 'groups' or 'roles' claim (Entra app roles, Okta groups)
    subjects: list[str] = Field(default_factory=list)  # stable ids: 'sub' (GitHub numeric id) or Entra 'oid'


class OAuthConfig(_Model):
    """Login through an identity provider; values may use the env:VAR form."""
    provider: OAuthProviderType
    client_id: str
    client_secret: str | None = None
    # Signs Teukhos's own tokens and encrypts stored sessions; keep it stable (>= 32 random bytes)
    signing_key: str
    tenant_id: str | None = None   # entra: the tenant GUID
    scope: str = "mcp.access"      # entra: a scope defined under 'Expose an API'
    extra_scopes: list[str] = Field(default_factory=list)  # oidc: e.g. [groups] for Okta's groups claim
    config_url: str | None = None  # oidc: https://<idp>/.well-known/openid-configuration
    verify_id_token: bool = False  # oidc: verify the id_token instead (e.g. Okta's org authorization server)
    redirect_uris: list[str] = Field(default_factory=list)  # extra client callbacks, e.g. Open WebUI
    consent: bool | str = True     # ask users to approve each new client; "remember" skips repeat prompts

    @model_validator(mode="after")
    def _check_provider(self) -> OAuthConfig:
        if self.provider == OAuthProviderType.entra and not (self.tenant_id and _GUID.fullmatch(self.tenant_id)):
            raise ValueError("auth.oauth.tenant_id must be your Entra tenant GUID "
                             "('common' or 'organizations' would reject every real token)")
        if self.provider == OAuthProviderType.oidc and not self.config_url:
            raise ValueError("auth.oauth.config_url is required for provider oidc")
        if self.provider in (OAuthProviderType.github, OAuthProviderType.entra, OAuthProviderType.google) \
                and not self.client_secret:
            raise ValueError(f"auth.oauth.client_secret is required for provider {self.provider.value}")
        if self.consent not in (True, "remember"):
            raise ValueError("auth.oauth.consent must be true or 'remember'")
        return self


class AuthConfig(_Model):
    mode: AuthMode = AuthMode.none
    api_keys: list[str] = Field(default_factory=list)
    oauth: OAuthConfig | None = None
    allow: AccessRule | None = None  # who may use this server at all (OAuth mode)

    @model_validator(mode="after")
    def _check_oauth(self) -> AuthConfig:
        if self.mode == AuthMode.oauth and self.oauth is None:
            raise ValueError("auth.mode oauth needs an auth.oauth block")
        if self.mode == AuthMode.oauth and self.oauth.provider in (OAuthProviderType.google,
                                                                   OAuthProviderType.github) and not self.allow:
            # Any Google or GitHub account in the world can sign in; the rule is what limits it
            raise ValueError(f"provider {self.oauth.provider.value} needs auth.allow "
                             "(e.g. domains: [example.com])")
        return self


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
    allow: AccessRule | None = None  # who may see and call this tool (OAuth mode, on top of auth.allow)
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

    @model_validator(mode="after")
    def _check_access(self) -> ForgeConfig:
        has_rules = self.auth.allow is not None or any(t.allow for t in self.tools)
        if has_rules and self.auth.mode != AuthMode.oauth:
            # Rules match OAuth identities; with API keys or no auth they would hide every tool
            raise ValueError("auth.allow and tools[].allow need auth.mode: oauth")
        if self.auth.mode == AuthMode.oauth and not self.server.public_url:
            raise ValueError("auth.mode oauth needs server.public_url (the https origin clients use)")
        return self


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
