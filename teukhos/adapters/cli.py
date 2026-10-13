"""CLI adapter — execute CLI commands as MCP tools."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import traceback

import anyio

from teukhos.adapters.base import AdapterResult, BaseAdapter
from teukhos.config import ArgConfig, ArgType, CLIAdapterConfig

logger = logging.getLogger("teukhos")

REDACTED = "[REDACTED]"

if os.name == "nt":
    # Windows searches the current directory before PATH for bare command names, so a
    # git.exe planted in an untrusted project would run instead of the real one.
    # Inherited by tools too, so their own scripts must call helpers by path.
    os.environ.setdefault("NoDefaultCurrentDirectoryInExePath", "1")
    # MSYS/Cygwin binaries (Git's usr\bin) glob-expand their own argv; with no shell
    # involved, '*' must stay literal or it can expand to dash-prefixed file names.
    for _var in ("MSYS", "CYGWIN"):
        if "noglob" not in os.environ.get(_var, ""):
            os.environ[_var] = f"{os.environ.get(_var, '')} noglob".strip()

# cmd.exe re-parses the arguments of .bat/.cmd files: these characters run commands,
# expand variables or split one value into several arguments, and cannot be quoted safely.
BATCH_UNSAFE_CHARS = '"%!^&|<>(),;=\x0b\x0c'


def _is_batch(command: str) -> bool:
    # Windows ignores trailing dots and spaces in file names
    return os.name == "nt" and command.rstrip(". ").lower().endswith((".bat", ".cmd"))


def _check_batch_args(command: str, values: list[str]) -> None:
    for value in values:
        if any(c in BATCH_UNSAFE_CHARS or (c.isspace() and c not in " \t") for c in value):
            raise ValueError(
                f"Arguments for batch file '{command}' must not contain any of "
                f"{BATCH_UNSAFE_CHARS[:-2]} or line breaks"
            )


def _find_batch_shim(command: str) -> str | None:
    """Resolve a bare name like 'npx' to its .cmd/.bat shim; CreateProcess only tries .exe."""
    if os.path.dirname(command) or os.path.splitext(command)[1]:
        return None
    resolved = shutil.which(command)
    # Relative hits come from the current directory (Python 3.11 which()) and are ignored
    return resolved if resolved and os.path.isabs(resolved) and _is_batch(resolved) else None


def _ansi_view(value: str) -> str:
    """The value as a non-Unicode Windows program receives it: best-fit maps e.g. U+FF0D to '-'."""
    import ctypes

    if "\0" in value:
        raise ValueError("embedded null character")
    convert = ctypes.windll.kernel32.WideCharToMultiByte
    size = convert(0, 0, value, -1, None, 0, None, None)
    buf = ctypes.create_string_buffer(size)
    convert(0, 0, value, -1, buf, size, None, None)
    return buf.value.decode("mbcs", errors="replace")


class CLIAdapter(BaseAdapter):
    """Adapter that wraps CLI binaries as MCP tools."""

    def __init__(self, cli_config: CLIAdapterConfig, arg_configs: list[ArgConfig]):
        self.cli_config = cli_config
        self.arg_configs = {a.name: a for a in arg_configs}
        # Operator-held secret defaults, longest first so overlapping values are fully replaced
        self.secrets = sorted(
            {a.default for a in arg_configs if a.secret and isinstance(a.default, str) and a.default},
            key=len, reverse=True,
        )

    def redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, REDACTED)
        return text

    async def execute(self, **kwargs: object) -> AdapterResult:
        """Build and run the CLI command from provided arguments."""
        command = self.cli_config.command
        timeout = self.cli_config.timeout_seconds
        try:
            cmd = self._build_command(**kwargs)
            agent_args = cmd[1 + len(self.cli_config.subcommand):]
            if _is_batch(cmd[0]):
                _check_batch_args(cmd[0], agent_args)
            env = {**os.environ, **self.cli_config.env} if self.cli_config.env else None
            cwd = os.path.expanduser(self.cli_config.working_dir) if self.cli_config.working_dir else None
            if cwd and not os.path.isdir(cwd):
                return self._failure(f"working_dir '{cwd}' does not exist or is not a directory")

            # Temp files instead of pipes: memory stays bounded by max_output_bytes, and
            # grandchildren holding the output open cannot stall a timeout (Windows).
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                def run(argv: list[str]):
                    return anyio.to_thread.run_sync(lambda: subprocess.run(
                        argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                        env=env, cwd=cwd, timeout=timeout,
                    ))

                try:
                    try:
                        result = await run(cmd)
                    except FileNotFoundError as e:
                        shim = _find_batch_shim(cmd[0]) if getattr(e, "winerror", None) == 2 else None
                        if shim is None:
                            raise
                        _check_batch_args(shim, agent_args)
                        result = await run([shim, *cmd[1:]])
                except subprocess.TimeoutExpired:
                    return self._failure(f"Tool timed out after {timeout}s")
                stdout, truncated = self._read_output(out)
                stderr, _ = self._read_output(err)
                return AdapterResult(stdout, stderr, result.returncode, truncated=truncated)
        except ValueError as e:  # rejected argument values, embedded NUL bytes
            logger.error(f"The error message: {e}, {traceback.format_exc()}")
            return self._failure(str(e))
        except OSError as e:
            # WinError 206 (command line too long) also arrives as FileNotFoundError
            if isinstance(e, FileNotFoundError) and getattr(e, "winerror", None) != 206:
                return self._failure(f"Command '{command}' not found. Is it installed and on PATH?")
            logger.error(f"The error message: {e}, {traceback.format_exc()}")
            return self._failure(f"Failed to run '{command}': {e}")

    @staticmethod
    def _failure(message: str) -> AdapterResult:
        return AdapterResult("", message, -1, failed=True)

    def _read_output(self, f) -> tuple[str, bool]:
        """Read captured output, redacted, then truncated to max_output_bytes."""
        limit = self.cli_config.max_output_bytes
        size = f.seek(0, os.SEEK_END)
        f.seek(0)
        # Read past the limit by the longest secret so one cut at the limit can't expose a prefix
        extra = len(self.secrets[0].encode()) if self.secrets else 0
        text = self.redact(f.read(limit + extra).decode("utf-8", errors="replace"))
        if size <= limit:
            return text, False
        text = text.encode()[:limit].decode("utf-8", errors="ignore")
        return f"{text}\n[output truncated: {size} bytes, showing first {limit}]", True

    def _build_command(self, **kwargs: object) -> list[str]:
        """Build the full command list from config + arguments."""
        cmd: list[str] = [self.cli_config.command]
        cmd.extend(self.cli_config.subcommand)

        positionals: list[str] = []

        for arg_name, arg_config in self.arg_configs.items():
            value = kwargs.get(arg_name, arg_config.default)
            if value is None:
                continue

            # A bare value starting with '-' would be parsed as an option (argument injection).
            # Enum values and the configured default are chosen by the operator, so they are trusted.
            if (
                (arg_config.positional or not arg_config.flag)
                and arg_config.type != ArgType.boolean
                and not arg_config.enum
                and value != arg_config.default
                and (str(value).startswith("-") or (os.name == "nt" and _ansi_view(str(value)).startswith("-")))
            ):
                raise ValueError(f"Argument '{arg_name}' must not start with '-'")

            # Non-Unicode Windows programs see look-alikes such as U+FF02 as a real '"',
            # which breaks the argument quoting
            if os.name == "nt" and '"' not in str(value) and '"' in _ansi_view(str(value)):
                raise ValueError(f"Argument '{arg_name}' contains a character that Windows converts to '\"'")

            if arg_config.positional:
                positionals.append(str(value))
                continue

            if arg_config.type == ArgType.boolean:
                if value is True and arg_config.flag:
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
