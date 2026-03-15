"""Installer plugin registry."""

from __future__ import annotations

from teukhos.installers.base import BaseInstaller, InstallScope
from teukhos.installers.claude_desktop import ClaudeDesktopInstaller
from teukhos.installers.claude_code import ClaudeCodeInstaller
from teukhos.installers.cursor import CursorInstaller
from teukhos.installers.github_copilot import GitHubCopilotInstaller
from teukhos.installers.gemini_cli import GeminiCLIInstaller
from teukhos.installers.codex import CodexInstaller
from teukhos.installers.windsurf import WindsurfInstaller
from teukhos.installers.cline import ClineInstaller
from teukhos.installers.roo_code import RooCodeInstaller
from teukhos.installers.continue_dev import ContinueDevInstaller
from teukhos.installers.kiro import KiroInstaller
from teukhos.installers.auggie import AuggieInstaller
from teukhos.installers.codebuddy import CodeBuddyInstaller
from teukhos.installers.opencode import OpenCodeInstaller
from teukhos.installers.trae import TraeInstaller

ALL_INSTALLERS: list[type[BaseInstaller]] = [
    ClaudeDesktopInstaller,
    ClaudeCodeInstaller,
    CursorInstaller,
    GitHubCopilotInstaller,
    GeminiCLIInstaller,
    CodexInstaller,
    WindsurfInstaller,
    ClineInstaller,
    RooCodeInstaller,
    ContinueDevInstaller,
    KiroInstaller,
    AuggieInstaller,
    CodeBuddyInstaller,
    OpenCodeInstaller,
    TraeInstaller,
]

__all__ = [
    "ALL_INSTALLERS",
    "BaseInstaller",
    "InstallScope",
]


def get_installer(slug: str) -> BaseInstaller | None:
    """Get an installer instance by slug."""
    for cls in ALL_INSTALLERS:
        if cls.slug == slug:
            return cls()
    return None


def get_all_installers() -> list[BaseInstaller]:
    """Get instances of all registered installers."""
    return [cls() for cls in ALL_INSTALLERS]


def discover_clients() -> list[BaseInstaller]:
    """Return installer instances for detected (installed) clients."""
    return [inst for inst in get_all_installers() if inst.detect()]
