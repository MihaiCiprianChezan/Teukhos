"""Access rules: who may see and call a tool, decided from the identity provider's token claims."""

from __future__ import annotations

from dataclasses import dataclass

from fastmcp.server.auth import AccessToken, AuthCheck, AuthContext

from teukhos.config import AccessRule, OAuthProviderType


@dataclass(frozen=True)
class Identity:
    email: str | None
    domain: str | None
    groups: frozenset[str]
    subjects: frozenset[str]


def identity(token: AccessToken, provider: OAuthProviderType) -> Identity:
    """Normalise provider claims. Only stable, verified values: no display names or usernames,
    which users can change (Entra preferred_username/upn, GitHub login)."""
    claims = token.claims or {}
    upstream = claims.get("upstream_claims") or {}  # Entra: a copy of the id claims

    def get(name: str):
        return claims.get(name) or upstream.get(name)

    email = get("email") if claims.get("email_verified", True) is not False else None
    email = str(email).lower() if email else None
    if provider == OAuthProviderType.google:
        # Workspace domain from Google's userinfo; no email-suffix fallback (gmail.com is not an org)
        domain = (claims.get("google_user_data") or {}).get("hd")
    else:
        domain = email.rsplit("@", 1)[1] if email and "@" in email else None

    groups: set[str] = set()
    for name in ("groups", "roles"):
        value = get(name) or []
        groups.update([value] if isinstance(value, str) else map(str, value))

    subjects = {str(v) for v in (claims.get("sub"), upstream.get("sub"), get("oid"), token.subject) if v}
    return Identity(email, domain.lower() if domain else None, frozenset(groups), frozenset(subjects))


def allows(rule: AccessRule, who: Identity) -> bool:
    """Any match allows: email, email domain, group/role, or subject id."""
    return bool(
        (who.email and who.email in {e.lower() for e in rule.emails})
        or (who.domain and who.domain in {d.lower() for d in rule.domains})
        or who.groups & set(rule.groups)
        or who.subjects & set(rule.subjects)
    )


def auth_check(rules: list[AccessRule | None], provider: OAuthProviderType) -> AuthCheck | None:
    """An auth check for mcp.tool(auth=...): every given rule must allow. A denied tool is hidden
    from tools/list and calling it reports 'Unknown tool'. fastmcp skips checks over stdio."""
    active = [r for r in rules if r is not None]
    if not active:
        return None

    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return False
        who = identity(ctx.token, provider)
        return all(allows(rule, who) for rule in active)

    return check
