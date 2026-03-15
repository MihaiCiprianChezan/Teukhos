"""API key resolution and authentication utilities."""

from __future__ import annotations

import os


def resolve_key(value: str) -> str:
    """Resolve an API key value.

    If the value starts with 'env:', read from the named environment variable.
    Otherwise, use the value as a literal key.

    Raises:
        ValueError: If env var is referenced but not set or empty, or if env:
            prefix has no variable name.
    """
    if value.startswith("env:"):
        env_var = value[4:]
        if not env_var:
            raise ValueError("env: prefix requires a variable name (e.g., 'env:TEUKHOS_API_KEY')")
        key = os.environ.get(env_var)
        if key is None:
            raise ValueError(f"Environment variable '{env_var}' is not set")
        if not key:
            raise ValueError(f"Environment variable '{env_var}' is set but empty")
        return key
    return value
