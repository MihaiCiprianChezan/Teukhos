"""CLI adapter — execute CLI commands as MCP tools."""

from __future__ import annotations

import shutil

import anyio

from mcpforge.adapters.base import AdapterResult, BaseAdapter
from mcpforge.config import ArgConfig, ArgType, CLIAdapterConfig


class CLIAdapter(BaseAdapter):
    """Adapter that wraps CLI binaries as MCP tools."""

    def __init__(self, cli_config: CLIAdapterConfig, arg_configs: list[ArgConfig]):
        self.cli_config = cli_config
        self.arg_configs = {a.name: a for a in arg_configs}

    async def execute(self, **kwargs: object) -> AdapterResult:
        """Build and run the CLI command from provided arguments."""
        cmd = self._build_command(**kwargs)
        env = self.cli_config.env if self.cli_config.env else None
        cwd = self.cli_config.working_dir

        try:
            with anyio.fail_after(self.cli_config.timeout_seconds):
                result = await anyio.run_process(
                    cmd,
                    env=env,
                    cwd=cwd,
                    check=False,
                )
        except TimeoutError:
            return AdapterResult(
                stdout="",
                stderr=f"Tool timed out after {self.cli_config.timeout_seconds}s",
                exit_code=-1,
            )
        except FileNotFoundError:
            return AdapterResult(
                stdout="",
                stderr=f"Command '{self.cli_config.command}' not found. Is it installed and on PATH?",
                exit_code=-1,
            )

        return AdapterResult(
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"),
            exit_code=result.returncode,
        )

    def _build_command(self, **kwargs: object) -> list[str]:
        """Build the full command list from config + arguments."""
        cmd: list[str] = [self.cli_config.command]
        cmd.extend(self.cli_config.subcommand)

        # Collect positional args to append at the end
        positionals: list[str] = []

        for arg_name, arg_config in self.arg_configs.items():
            value = kwargs.get(arg_name, arg_config.default)
            if value is None:
                continue

            if arg_config.positional:
                positionals.append(str(value))
                continue

            if arg_config.type == ArgType.boolean:
                if value is True:
                    if arg_config.flag:
                        cmd.append(arg_config.flag)
                continue

            if arg_config.flag:
                cmd.append(arg_config.flag)
                cmd.append(str(value))
            else:
                cmd.append(str(value))

        cmd.extend(positionals)
        return cmd

    def check_binary(self) -> str | None:
        """Check if the command binary is available. Returns error message or None."""
        binary = self.cli_config.command
        if shutil.which(binary) is None:
            return f"Command '{binary}' not found. Is it installed and on PATH?"
        return None
