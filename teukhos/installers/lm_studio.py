"""Installer for LM Studio."""
from __future__ import annotations
from pathlib import Path
from teukhos.installers.base import InstallScope, JsonMcpInstaller


def lm_studio_home() -> Path:
    """Same lookup as LM Studio's own findLMStudioHome: pointer file, legacy cache dir, ~/.lmstudio."""
    pointer = Path.home() / ".lmstudio-home-pointer"
    if pointer.exists() and pointer.read_text(encoding="utf-8").strip():
        return Path(pointer.read_text(encoding="utf-8").strip())
    legacy = Path.home() / ".cache" / "lm-studio"
    return legacy if legacy.exists() else Path.home() / ".lmstudio"


class LMStudioInstaller(JsonMcpInstaller):
    name = "LM Studio"
    slug = "lm-studio"
    supported_scopes = [InstallScope.global_]
    env_ref = None  # variable substitution in mcp.json is not documented

    def default_path(self, scope: InstallScope) -> Path:
        return lm_studio_home() / "mcp.json"
