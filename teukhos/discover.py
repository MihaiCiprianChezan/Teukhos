"""Discover CLI tools from --help output and generate teukhos.yaml configs."""

from __future__ import annotations

import keyword
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath

import yaml
from rich.console import Console

console = Console(stderr=True)

# Python reserved keywords that can't be used as parameter names
_PYTHON_RESERVED = set(keyword.kwlist) | {"True", "False", "None"}


@dataclass
class DiscoveredArg:
    name: str
    flag: str | None = None
    short_flag: str | None = None
    description: str = ""
    required: bool = False
    positional: bool = False
    arg_type: str = "string"
    default: str | None = None
    is_boolean: bool = False


@dataclass
class DiscoveredCommand:
    name: str
    description: str = ""
    subcommands: list[str] = field(default_factory=list)
    args: list[DiscoveredArg] = field(default_factory=list)
    positional_args: list[DiscoveredArg] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    binary: str
    binary_name: str
    description: str = ""
    tools: list[DiscoveredCommand] = field(default_factory=list)


def run_help(binary: str, args: list[str] | None = None, timeout: int = 15) -> str | None:
    """Run binary with --help and capture stdout+stderr."""
    cmd = [binary] + (args or []) + ["--help"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout or result.stderr
        return output.strip() if output else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        console.print(f"[dim]Failed to run {' '.join(cmd)}: {e}[/]")
        return None


def parse_commands(help_text: str) -> list[tuple[str, str]]:
    """Extract command names and descriptions from a Commands: section.

    Examples:
        Basic \"Commands:\" section:

        >>> sample = '''
        ... Usage: tool [OPTIONS] COMMAND [ARGS]...
        ...
        ... Commands:
        ...   init        Initialize the repository
        ...   status      Show the current status
        ... '''
        >>> parse_commands(sample)
        [('init', 'Initialize the repository'), ('status', 'Show the current status')]
    """
    commands: list[tuple[str, str]] = []
    seen: set[str] = set()
    in_commands = False
    for line in help_text.splitlines():
        stripped = line.strip()
        lower = stripped.lower()
        # Match section headers like "Commands:", "CORE COMMANDS", "ADDITIONAL COMMANDS",
        # "The following commands are available:", "Subcommands:", etc.
        if (
            lower.startswith("commands:")
            or lower.startswith("subcommands:")
            or lower.startswith("subgroups:")
            or "commands are available" in lower
            or "the following commands" in lower
            or re.match(r"^[\w\s]*commands?\s*$", lower)
        ):
            in_commands = True
            continue
        if in_commands:
            if not stripped:
                continue
            # Non-indented non-empty line = likely a new section header
            if not line.startswith(" ") and not line.startswith("\t"):
                # But it might be another COMMANDS section (e.g. "ADDITIONAL COMMANDS")
                if re.match(r"^[\w\s]*commands?\s*$", lower):
                    continue  # stay in commands mode
                in_commands = False
                continue
            # Indented line that looks like an options/flags header = stop
            if re.match(r"^\s*(the following )?(options|flags|inherited)", stripped, re.IGNORECASE):
                in_commands = False
                continue
            # Parse "command-name   Description text"
            match = re.match(r"^\s+([\w][\w\-]*(?:\s+<[^>]+>)*)\s{2,}(.+)$", line)
            if not match:
                # Try gh-style: "  name:  Description" (colon after command name)
                match = re.match(r"^\s+([\w][\w\-]*):\s+(.+)$", line)
            if match:
                cmd_part = match.group(1).strip()
                desc = match.group(2).strip()
                cmd_name = cmd_part.split()[0]
                if cmd_name not in seen:
                    seen.add(cmd_name)
                    commands.append((cmd_name, desc))
    return commands


def parse_options(help_text: str) -> list[DiscoveredArg]:
    """Extract options/arguments from help text.

    The parser is intentionally conservative and targets common CLI help formats.

    Examples:
        Simple GNU-style options section:

        >>> help_text = '''
        ... Options:
        ...   -f, --force           Force the operation
        ...   --count <INT>         Number of items
        ...   -v, --verbose         Enable verbose output
        ... '''
        >>> opts = parse_options(help_text)
        >>> [o.flag for o in opts]
        ['--force', '--count', '--verbose']
        >>> [o.short_flag for o in opts]
        ['-f', None, '-v']
    """
    args: list[DiscoveredArg] = []
    seen_names: set[str] = set()

    # Skip common global flags that aren't tool-specific
    skip_flags = {
        "--help", "-h", "-?", "--version",
        # Azure CLI global args
        "--debug", "--only-show-errors", "--output", "--query", "--subscription", "--verbose",
    }

    for line in help_text.splitlines():
        stripped = line.strip()
        if not stripped or not stripped.startswith("-"):
            continue

        # Parse option lines in several formats:
        # 1) -f, --flag <value>  Description (REQUIRED) [default: x]
        # 2) --flag  Description
        # 3) -v,--version  Description (winget style)
        # 4) --flag -f : Description (Azure CLI style)
        match = re.match(
            r"^\s*"
            r"(?:(-\w),\s*)?"  # optional short flag with comma+optional space
            r"(--[\w][\w\-]*)"  # long flag
            r"(?:\s+<([^>]+)>)?"  # optional value placeholder
            r"\s{2,}"  # separator
            r"(.+)$",  # description
            line,
        )
        if not match:
            # Azure CLI style: --long-flag -s  : Description
            match_az = re.match(
                r"^\s*"
                r"(--[\w][\w\-]*)"  # long flag
                r"(?:\s+(-\w))?"  # optional short flag after
                r"\s+:\s+"  # colon separator
                r"(.+)$",  # description
                line,
            )
            if match_az:
                long_flag = match_az.group(1)
                short_flag = match_az.group(2)
                value_hint = None
                desc = match_az.group(3).strip()
            else:
                continue
        else:
            short_flag = match.group(1)
            long_flag = match.group(2)
            value_hint = match.group(3)
            desc = match.group(4).strip()

        if long_flag in skip_flags or short_flag in skip_flags:
            continue

        # Derive a clean snake_case name from the flag, avoiding Python reserved keywords
        name = long_flag.lstrip("-").replace("-", "_")
        if name in _PYTHON_RESERVED:
            name = f"{name}_value"
        if name in seen_names:
            continue
        seen_names.add(name)

        required = "(REQUIRED)" in desc
        desc_clean = desc.replace("(REQUIRED)", "").strip()

        # Extract default value
        default = None
        default_match = re.search(r"\[default:\s*([^\]]+)\]", desc_clean)
        if default_match:
            default = default_match.group(1).strip()
            desc_clean = re.sub(r"\s*\[default:\s*[^\]]+\]", "", desc_clean).strip()

        # Determine type
        is_boolean = value_hint is None and not required
        arg_type = "string"
        if is_boolean:
            arg_type = "boolean"
        elif value_hint:
            hint_lower = value_hint.lower()
            if hint_lower in ("limit", "duration", "count", "port"):
                arg_type = "integer"

        # If default is a number, hint at integer
        if default and arg_type == "string":
            try:
                int(default)
                arg_type = "integer"
            except ValueError:
                pass

        args.append(DiscoveredArg(
            name=name,
            flag=long_flag,
            short_flag=short_flag,
            description=desc_clean,
            required=required,
            arg_type=arg_type,
            default=default,
            is_boolean=is_boolean,
        ))

    return args


def parse_positional_args(help_text: str) -> list[DiscoveredArg]:
    """Extract positional arguments from an Arguments: section."""
    positionals: list[DiscoveredArg] = []
    in_args = False
    for line in help_text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("arguments:"):
            in_args = True
            continue
        if in_args:
            if not stripped:
                continue
            if not line.startswith(" ") and not line.startswith("\t"):
                break
            match = re.match(r"^\s+<([\w\-]+)>\s{2,}(.+)$", line)
            if match:
                name = match.group(1).replace("-", "_")
                desc = match.group(2).strip()
                positionals.append(DiscoveredArg(
                    name=name,
                    description=desc,
                    required=True,
                    positional=True,
                ))
    return positionals


def _extract_description(help_text: str) -> str:
    """Extract a human-friendly description from --help output.

    Prefers the body under a "Description:" section when present; otherwise,
    uses the first non-empty line that isn't a common header like "Usage:".
    """
    lines = help_text.splitlines()

    # 1) Look for an explicit "Description:" section and take the text under it.
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            desc_lines: list[str] = []
            for follow in lines[i + 1 :]:
                follow_stripped = follow.strip()
                if not follow_stripped:
                    break
                lower = follow_stripped.lower()
                if lower.startswith(("usage", "options", "commands", "subcommands", "arguments")):
                    break
                desc_lines.append(follow_stripped)
            result = " ".join(desc_lines).strip()
            if result:
                return result

    # 2) Fallback: first non-empty line that isn't a common header.
    #    "Skip" headers like Usage: that are single lines.
    #    "Stop" at section headers that contain structured content (commands,
    #    options, arguments) — anything indented after them is not a description.
    skip_prefixes = ("usage", "group")
    stop_prefixes = (
        "options",
        "available commands",
        "commands",
        "subcommands",
        "arguments",
        "positional arguments",
    )
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(lower.startswith(p + ":") or lower == p for p in stop_prefixes):
            break
        # Also stop on multi-word command section headers like "CORE COMMANDS"
        if re.match(r"^[\w\s]*commands?\s*$", lower):
            break
        if any(lower.startswith(p + ":") or lower == p for p in skip_prefixes):
            continue
        return stripped

    return ""


def discover_binary(
    binary_path: str,
    max_depth: int = 2,
    filter_prefix: list[str] | None = None,
    timeout: int = 15,
) -> DiscoveryResult:
    """Discover all tools from a binary by recursively parsing --help output.

    Args:
        binary_path: Path or name of the binary.
        max_depth: Maximum recursion depth for subcommands (default 2).
        filter_prefix: Only discover subcommands under this prefix path
                       (e.g. ["vm"] for "az vm ...").
        timeout: Timeout in seconds for each --help subprocess call (default 15).
    """
    binary_name = PureWindowsPath(binary_path).stem.lower().replace(" ", "-")

    # If filter_prefix is set, start from that subtree
    start_args = filter_prefix or []
    top_help = run_help(binary_path, start_args if start_args else None, timeout=timeout)
    if not top_help:
        raise RuntimeError(f"Could not get --help output from: {binary_path}")

    description = _extract_description(top_help)

    result = DiscoveryResult(
        binary=binary_path,
        binary_name=binary_name,
        description=description,
    )

    def _recurse(help_text: str, cmd_path: list[str], depth: int) -> None:
        """Recursively discover subcommands up to max_depth."""
        commands = parse_commands(help_text)

        if commands and depth < max_depth:
            for cmd_name, cmd_desc in commands:
                full_path = cmd_path + [cmd_name]
                label = " ".join(full_path)
                console.print(f"[dim]  Discovering: {label}...[/]")
                sub_help = run_help(binary_path, full_path, timeout=timeout)
                if not sub_help:
                    continue
                # Recurse deeper
                _recurse(sub_help, full_path, depth + 1)
        elif commands and depth >= max_depth:
            # At max depth but still has subcommands — register each as a leaf
            for cmd_name, cmd_desc in commands:
                full_path = cmd_path + [cmd_name]
                label = " ".join(full_path)
                console.print(f"[dim]  Discovering: {label}...[/]")
                sub_help = run_help(binary_path, full_path, timeout=timeout)
                if not sub_help:
                    continue
                tool_name = "_".join(full_path).replace("-", "_")
                result.tools.append(DiscoveredCommand(
                    name=tool_name,
                    description=cmd_desc,
                    subcommands=list(full_path),
                    args=parse_options(sub_help),
                    positional_args=parse_positional_args(sub_help),
                ))
        else:
            # Leaf command — no subcommands
            if cmd_path:
                tool_name = "_".join(cmd_path).replace("-", "_")
                leaf_desc = _extract_description(help_text)
                result.tools.append(DiscoveredCommand(
                    name=tool_name,
                    description=leaf_desc or description,
                    subcommands=list(cmd_path),
                    args=parse_options(help_text),
                    positional_args=parse_positional_args(help_text),
                ))
            else:
                # No subcommands at all — the binary itself is one tool
                result.tools.append(DiscoveredCommand(
                    name=binary_name.replace("-", "_"),
                    description=description,
                    args=parse_options(help_text),
                    positional_args=parse_positional_args(help_text),
                ))

    _recurse(top_help, list(start_args), 0)
    return result


def generate_yaml(result: DiscoveryResult, exec_timeout: int | None = None) -> str:
    """Generate a teukhos.yaml config from discovery results."""
    config: dict = {
        "forge": {
            "name": result.binary_name,
            "description": result.description,
        },
        "tools": [],
    }

    for tool in result.tools:
        tool_entry: dict = {
            "name": tool.name,
            "description": tool.description,
            "adapter": "cli",
            "cli": {
                "command": result.binary,
                "subcommand": tool.subcommands,
                **({"timeout_seconds": exec_timeout} if exec_timeout is not None else {}),
            },
        }

        args_list: list[dict] = []

        # Positional args first
        for arg in tool.positional_args:
            entry: dict = {
                "name": arg.name,
                "type": "string",
                "description": arg.description,
                "required": True,
                "positional": True,
            }
            args_list.append(entry)

        # Flag args
        for arg in tool.args:
            entry = {
                "name": arg.name,
                "type": arg.arg_type,
                "description": arg.description,
            }
            if arg.flag:
                entry["flag"] = arg.flag
            if arg.required:
                entry["required"] = True
            if arg.default is not None:
                # Coerce default to the right type
                if arg.arg_type == "integer":
                    try:
                        entry["default"] = int(arg.default)
                    except ValueError:
                        entry["default"] = arg.default
                else:
                    entry["default"] = arg.default
            if arg.is_boolean:
                entry["type"] = "boolean"
            args_list.append(entry)

        if args_list:
            tool_entry["args"] = args_list

        tool_entry["output"] = {"type": "stdout"}
        config["tools"].append(tool_entry)

    return yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True)
