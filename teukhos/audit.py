"""Audit log: one JSON line per tool call (who, what, with which arguments, and the outcome)."""

from __future__ import annotations

import json
import logging
import os
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("teukhos")


class AuditLog:
    """Append-only JSONL file. Opened once at startup so a bad path fails fast."""

    def __init__(self, path: str):
        self.path = Path(os.path.expanduser(path))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8"):
            pass
        self._lock = threading.Lock()

    def record(self, **entry: Any) -> None:
        line = json.dumps(
            {"time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **entry},
            ensure_ascii=False,
            default=str,
        )
        try:
            with self._lock, open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            # A full disk must not take the tools down; the failure itself is logged
            logger.error(f"The error message: {e}, {traceback.format_exc()}")
