"""Output mapping — transform subprocess results into tool responses."""

from __future__ import annotations

import json

from mcpforge.config import OutputConfig, OutputType


class OutputMapper:
    """Maps subprocess output to the configured response format."""

    def __init__(self, config: OutputConfig):
        self.config = config

    def map(self, stdout: str, stderr: str, exit_code: int) -> str:
        """Map subprocess results to the configured output format."""
        match self.config.type:
            case OutputType.stdout:
                return stdout
            case OutputType.stderr:
                return stderr
            case OutputType.json_field:
                return self._extract_json_field(stdout)
            case OutputType.exit_code:
                return self._map_exit_code(exit_code)
        return stdout

    def _extract_json_field(self, stdout: str) -> str:
        """Parse JSON and extract a field by dot-notation path."""
        if not self.config.field:
            return stdout
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return f"Error: output is not valid JSON:\n{stdout[:500]}"
        parts = self.config.field.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return f"Error: index {idx} out of range in field '{self.config.field}'"
            else:
                return f"Error: field '{self.config.field}' not found in JSON output"
        if isinstance(current, (dict, list)):
            return json.dumps(current, indent=2)
        return str(current)

    def _map_exit_code(self, exit_code: int) -> str:
        """Map exit code to a human-readable message."""
        if self.config.exit_codes and exit_code in self.config.exit_codes:
            return self.config.exit_codes[exit_code]
        if exit_code == 0:
            return "Success (exit code 0)"
        return f"Failed with exit code {exit_code}"
