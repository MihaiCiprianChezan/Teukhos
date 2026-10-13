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
    failed: bool = False      # the adapter itself failed (timeout, not found, rejected args); stderr says why
    truncated: bool = False   # stdout was cut at max_output_bytes


class BaseAdapter(ABC):
    """Abstract base for all Teukhos adapters."""

    @abstractmethod
    async def execute(self, **kwargs: object) -> AdapterResult:
        """Execute the tool with the given arguments."""
        ...
