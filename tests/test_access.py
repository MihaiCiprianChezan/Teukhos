"""Tests for OAuth identities and per-tool access rules (no real identity provider needed)."""

import json
import sys

import pytest
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.utilities.tests import asgi_server
from pydantic import ValidationError

from teukhos.access import allows, identity
from teukhos.config import AccessRule, ArgConfig, ForgeConfig, OAuthProviderType
from teukhos.engine import build_server

TOKENS = {
    "t-alice": {"client_id": "alice", "scopes": [], "sub": "1", "email": "alice@acme.com", "groups": ["dev"]},
    "t-bob": {"client_id": "bob", "scopes": [], "sub": "2", "email": "Bob@Contractor.io", "roles": ["ops"]},
    "t-eve": {"client_id": "eve", "scopes": [], "sub": "3", "email": "eve@acme.com", "email_verified": False},
    "t-mallory": {"client_id": "m", "scopes": [], "sub": "4", "email": "mallory@gmail.com"},
}


def _config(tmp_path):
    tool = lambda name, **extra: {  # noqa: E731
        "name": name,
        "cli": {"command": sys.executable, "subcommand": ["-c", f"print('{name} ran')"]},
        **extra,
    }
    return ForgeConfig.model_validate({
        "server": {"transport": "http", "public_url": "http://localhost:8765",
                   "audit_log": str(tmp_path / "audit.jsonl")},
        "auth": {
            "mode": "oauth",
            "oauth": {"provider": "oidc", "client_id": "c", "signing_key": "k",
                      "config_url": "https://idp.example/.well-known/openid-configuration"},
            "allow": {"domains": ["acme.com", "contractor.io"]},
        },
        "tools": [tool("whoami"), tool("deploy", allow={"groups": ["ops"]})],
    })


@pytest.fixture
async def server(tmp_path):
    bundle = build_server(_config(tmp_path), auth=StaticTokenVerifier(tokens=TOKENS))
    async with asgi_server(bundle.mcp, transport="streamable-http") as srv:
        yield srv


async def _tools(server, token):
    async with server.client(auth=token) as c:
        return {t.name for t in await c.list_tools()}


async def test_rules_decide_which_tools_each_identity_sees(server):
    assert await _tools(server, "t-alice") == {"whoami"}              # domain ok, not in ops
    assert await _tools(server, "t-bob") == {"whoami", "deploy"}      # domain + ops role, case-insensitive
    assert await _tools(server, "t-eve") == set()                     # unverified email counts for nothing
    assert await _tools(server, "t-mallory") == set()                 # outside the allowed domains


async def test_hidden_tool_cannot_be_called_and_is_audited(server, tmp_path):
    async with server.client(auth="t-alice") as c:
        result = await c.call_tool("deploy", {}, raise_on_error=False)
        assert result.is_error and "Unknown tool" in result.content[0].text
    async with server.client(auth="t-bob") as c:
        assert "deploy ran" in (await c.call_tool("deploy", {})).content[0].text
    entries = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(e["user"], e["subject"], e["tool"], e["ok"]) for e in entries] == [
        ("alice@acme.com", "1", "deploy", False),
        ("bob@contractor.io", "2", "deploy", True),  # the identity the rules use, and the stable sub
    ]
    assert entries[0]["error"] == "unknown tool or not allowed"


async def test_mcp_needs_a_token_but_health_does_not(server):
    async with server.http_client() as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.post("/mcp", json={})).status_code == 401


def _token(**claims):
    return AccessToken(token="x", client_id="c", scopes=[], subject=claims.get("sub"), claims=claims)


def test_identity_uses_only_stable_verified_claims():
    entra = identity(_token(sub="pairwise", oid="oid-1", preferred_username="old@acme.com",
                            upstream_claims={"email": "a@acme.com", "roles": ["ops"]}), OAuthProviderType.entra)
    assert entra.email == "a@acme.com" and entra.domain == "acme.com"
    assert entra.groups == {"ops"} and {"pairwise", "oid-1"} <= entra.subjects

    google = identity(_token(sub="9", email="x@gmail.com", google_user_data={}), OAuthProviderType.google)
    assert google.domain is None  # no Workspace 'hd', and no fallback to the email suffix
    workspace = identity(_token(sub="9", email="x@acme.com", google_user_data={"hd": "acme.com"}),
                         OAuthProviderType.google)
    assert workspace.domain == "acme.com"

    github = identity(_token(sub="12345", login="octocat", email=None), OAuthProviderType.github)
    assert allows(AccessRule(subjects=["12345"]), github)
    assert not allows(AccessRule(emails=["octocat"]), github)


def test_empty_rule_allows_nobody():
    assert not allows(AccessRule(), identity(_token(sub="1", email="a@acme.com"), OAuthProviderType.oidc))


def test_rules_require_oauth_mode():
    with pytest.raises(ValidationError, match="need auth.mode: oauth"):
        ForgeConfig.model_validate({"tools": [{"name": "t", "allow": {"domains": ["acme.com"]}}]})


async def test_real_provider_metadata_and_redirect_allowlist(monkeypatch, tmp_path):
    """Build the actual Google OAuth proxy (no network needed) and check what ChatGPT/Claude see."""
    monkeypatch.setenv("FASTMCP_HOME", str(tmp_path / "fastmcp"))
    monkeypatch.setenv("TK_GOOGLE_SECRET", "s3cret")
    monkeypatch.setenv("TK_SIGNING_KEY", "k" * 32)
    config = ForgeConfig.model_validate({
        "server": {"transport": "http", "public_url": "https://tools.acme.com"},
        "auth": {"mode": "oauth", "allow": {"domains": ["acme.com"]},
                 "oauth": {"provider": "google", "client_id": "cid.apps.googleusercontent.com",
                           "client_secret": "env:TK_GOOGLE_SECRET", "signing_key": "env:TK_SIGNING_KEY"}},
        "tools": [],
    })
    bundle = build_server(config)
    async with asgi_server(bundle.mcp, transport="streamable-http") as srv, srv.http_client() as http:
        prm = (await http.get("/.well-known/oauth-protected-resource/mcp")).json()
        assert prm["resource"] == "https://tools.acme.com/mcp"
        meta = (await http.get("/.well-known/oauth-authorization-server")).json()
        assert meta["client_id_metadata_document_supported"] is True  # Claude/ChatGPT register by CIMD
        assert "resource_metadata" in (await http.post("/mcp", json={})).headers["www-authenticate"]

        def register(uri):
            return http.post("/register", json={"redirect_uris": [uri], "client_name": "t",
                                                "token_endpoint_auth_method": "none"})
        assert (await register("https://claude.ai/api/mcp/auth_callback")).status_code == 201
        assert (await register("http://127.0.0.1:33389/mcp-oauth-callback")).status_code == 201
        assert (await register("https://evil.example/callback")).status_code == 400


def test_google_string_email_verified_false_is_unverified():
    """Google's tokeninfo sends booleans as strings; "false" must not count as verified."""
    for value in ("false", "False", None, False):
        who = identity(_token(sub="9", email="alice@acme.com", email_verified=value), OAuthProviderType.google)
        assert who.email is None, value
    assert identity(_token(sub="9", email="Alice@Acme.com ", email_verified="true"),
                    OAuthProviderType.oidc).email == "alice@acme.com"


GUID = "11111111-2222-3333-4444-555555555555"


def _oauth(provider="oidc", allow=True, public_url="https://tools.acme.com", **oauth):
    oauth = {"provider": provider, "client_id": "c", "client_secret": "s", "signing_key": "k",
             "config_url": "https://idp/.well-known/openid-configuration", "tenant_id": GUID, **oauth}
    return {"server": {"transport": "http", "public_url": public_url},
            "auth": {"mode": "oauth", "oauth": oauth, **({"allow": {"domains": ["acme.com"]}} if allow else {})}}


@pytest.mark.parametrize("config, message", [
    (_oauth(allow=False), "needs auth.allow"),
    (_oauth("entra", allow=False), "needs auth.allow"),
    (_oauth("entra", tenant_id="organizations"), "tenant GUID"),
    (_oauth(config_url=None), "config_url is required"),
    (_oauth("github", client_secret=None), "client_secret is required"),
    (_oauth(consent=False), "consent must be"),
    (_oauth(public_url="http://tools.acme.com"), "must use https"),
    (_oauth(public_url="https://tools.acme.com/mcp"), "no path"),
    ({"auth": _oauth()["auth"]}, "needs server.public_url"),
])
def test_oauth_config_fails_closed(config, message):
    with pytest.raises(ValidationError, match=message):
        ForgeConfig.model_validate(config)


def test_public_url_is_canonical():
    """The Origin check compares exactly, and browsers send lowercase origins without :443."""
    for url in ("https://Tools.Acme.com", "https://tools.acme.com:443/", "https://TOOLS.acme.COM/"):
        assert ForgeConfig.model_validate(_oauth(public_url=url)).server.public_url == "https://tools.acme.com"
    assert ForgeConfig.model_validate(_oauth(public_url="http://localhost:8765")).server.public_url == \
        "http://localhost:8765"


def test_oidc_requests_extra_scopes_upstream(monkeypatch):
    """Clients usually ask only for the required scopes, so groups/offline_access are forced upstream."""
    import fastmcp.server.auth.oidc_proxy as oidc
    from teukhos.auth import build_oauth_provider
    captured = {}
    monkeypatch.setattr(oidc, "OIDCProxy", lambda **kwargs: captured.update(kwargs))
    config = ForgeConfig.model_validate(_oauth(extra_scopes=["groups"]))
    build_oauth_provider(config.auth.oauth, config.server.public_url)
    assert captured["extra_authorize_params"] == {"scope": "openid email profile offline_access groups"}
    assert captured["required_scopes"] == ["openid", "email", "profile"]


def test_github_asks_only_to_read_the_profile(monkeypatch, tmp_path):
    from teukhos.auth import build_oauth_provider
    monkeypatch.setenv("FASTMCP_HOME", str(tmp_path))
    config = ForgeConfig.model_validate(_oauth("github"))
    assert build_oauth_provider(config.auth.oauth, config.server.public_url).required_scopes == ["read:user"]


async def test_refused_arguments_and_long_names_are_audited(tmp_path):
    config = _config(tmp_path)
    config.tools[0].args = [ArgConfig(name="mode", flag="--mode", enum=["a", "b"])]
    bundle = build_server(config, auth=StaticTokenVerifier(tokens=TOKENS))
    async with asgi_server(bundle.mcp, transport="streamable-http") as srv, srv.client(auth="t-bob") as c:
        await c.call_tool("whoami", {"mode": "zzz"}, raise_on_error=False)
        await c.call_tool("x" * 5000, {}, raise_on_error=False)
    invalid, unknown = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert (invalid["tool"], invalid["error"], invalid["args"]) == ("whoami", "invalid arguments", None)
    assert unknown["tool"] == "x" * 200
