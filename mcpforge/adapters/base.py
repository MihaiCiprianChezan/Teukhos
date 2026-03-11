"""Base adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AdapterResult:
    """Result from running an adapter."""
    stdout: str
    stderr: str
    exit_code: int


class BaseAdapter(ABC):
    """Abstract base for all MCPForge adapters."""

    @abstractmethod
    async def execute(self, **kwargs: object) -> AdapterResult:
        """Execute the tool with the given arguments."""
        ...
