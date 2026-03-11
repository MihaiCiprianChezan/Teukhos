"""MCPForge CLI — Typer-based command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from mcpforge import __version__
from mcpforge.config import TransportType, load_config

app = typer.Typer(
    name="mcp-forge",
    help="Spawn MCP servers from declarative YAML configuration.",
    no_args_is_help=True,
)
console = Console()

DEFAULT_CONFIG = "mcp-forge.yaml"


@app.command()
def serve(
    config: Annotated[
        Path, typer.Argument(help="Path to mcp-forge.yaml config file")
    ] = Path(DEFAULT_CONFIG),
    transport: Annotated[
        Optional[str], typer.Option("--transport", "-t", help="Override transport (stdio/http)")
    ] = None,
    port: Annotated[
        Optional[int], typer.Option("--port", "-p", help="Override HTTP port")
    ] = None,
) -> None:
    """Start the MCPForge MCP server."""
    try:
        forge_config = load_config(config)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Config validation error:[/] {e}")
        raise typer.Exit(1)

    # Apply CLI overrides
    if transport:
        try:
            forge_config.server.transport = TransportType(transport)
        except ValueError:
            console.print(f"[bold red]Error:[/] Invalid transport '{transport}'. Use 'stdio' or 'http'.")
            raise typer.Exit(1)
    if port:
        forge_config.server.port = port

    # Check binaries
    from mcpforge.adapters.cli import CLIAdapter

    for tool in forge_config.tools:
        if tool.adapter == "cli" and tool.cli:
            adapter = CLIAdapter(tool.cli, tool.args)
            warning = adapter.check_binary()
            if warning:
                console.print(f"[bold yellow]Warning:[/] Tool '{tool.name}': {warning}")

    # Security warning
    if (
        forge_config.server.transport == TransportType.http
        and forge_config.server.host == "0.0.0.0"
        and forge_config.auth.mode.value == "none"
    ):
        console.print(
            Panel(
                "[bold red]WARNING:[/] Server is binding to 0.0.0.0 with no authentication!\n"
                "This exposes your tools to the network. Add auth or use 127.0.0.1.",
                title="Security Warning",
                border_style="red",
            )
        )

    # Print startup banner
    _print_banner(forge_config)

    # Build and run
    from mcpforge.engine import build_server

    mcp = build_server(forge_config)

    if forge_config.server.transport == TransportType.http:
        mcp.run(
            transport="streamable-http",
            host=forge_config.server.host,
            port=forge_config.server.port,
        )
    else:
        mcp.run(transport="stdio")


@app.command()
def validate(
    config: Annotated[
        Path, typer.Argument(help="Path to mcp-forge.yaml config file")
    ] = Path(DEFAULT_CONFIG),
) -> None:
    """Validate a mcp-forge.yaml config file."""
    try:
        forge_config = load_config(config)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Validation error:[/] {e}")
        raise typer.Exit(1)

    console.print(f"[bold green]Valid![/] {len(forge_config.tools)} tool(s) defined.")
    table = Table(title="Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Adapter", style="magenta")
    table.add_column("Description")
    for tool in forge_config.tools:
        table.add_row(tool.name, tool.adapter, tool.description)
    console.print(table)


@app.command()
def version() -> None:
    """Print MCPForge version."""
    console.print(f"MCPForge v{__version__}")


@app.command(name="wait-ready")
def wait_ready(
    host: Annotated[str, typer.Option("--host", help="Server host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", "-p", help="Server port")] = 8765,
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout in seconds")] = 30,
) -> None:
    """Poll /health until server is ready. For CI/CD pipelines."""
    import time

    import httpx

    url = f"http://{host}:{port}/health"
    start = time.monotonic()
    console.print(f"Waiting for server at {url} ...")

    while time.monotonic() - start < timeout:
        try:
            resp = httpx.get(url, timeout=2)
            if resp.status_code == 200:
                console.print(f"[bold green]Server is ready![/]")
                raise typer.Exit(0)
        except httpx.ConnectError:
            pass
        time.sleep(1)

    console.print(f"[bold red]Timeout:[/] Server not ready after {timeout}s")
    raise typer.Exit(1)


@app.command()
def install(
    config: Annotated[Path, typer.Argument(help="Path to mcp-forge.yaml config file")],
    client: Annotated[
        str, typer.Option("--client", "-c", help="Target client (claude-desktop)")
    ] = "claude-desktop",
) -> None:
    """Install MCPForge config into a client (e.g. Claude Desktop)."""
    import json
    import shutil

    if client != "claude-desktop":
        console.print(f"[bold red]Error:[/] Unsupported client '{client}'. Only 'claude-desktop' is supported.")
        raise typer.Exit(1)

    config_path = config.resolve()
    if not config_path.exists():
        console.print(f"[bold red]Error:[/] Config file not found: {config_path}")
        raise typer.Exit(1)

    # Find Claude Desktop config
    mcp_forge_bin = shutil.which("mcp-forge") or "mcp-forge"

    try:
        forge_config = load_config(config_path)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)

    server_name = f"mcpforge-{forge_config.forge.name}"
    entry = {
        "command": mcp_forge_bin,
        "args": ["serve", str(config_path)],
    }

    # Determine Claude Desktop config location
    import platform
    system = platform.system()
    if system == "Darwin":
        claude_config = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        claude_config = Path.home() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    else:
        claude_config = Path.home() / ".config" / "claude" / "claude_desktop_config.json"

    # Load or create config
    if claude_config.exists():
        with open(claude_config) as f:
            desktop_config = json.load(f)
    else:
        claude_config.parent.mkdir(parents=True, exist_ok=True)
        desktop_config = {}

    if "mcpServers" not in desktop_config:
        desktop_config["mcpServers"] = {}

    desktop_config["mcpServers"][server_name] = entry

    with open(claude_config, "w") as f:
        json.dump(desktop_config, f, indent=2)

    console.print(f"[bold green]Installed![/] Added '{server_name}' to {claude_config}")
    console.print("Restart Claude Desktop to pick up the changes.")


@app.command()
def discover(
    binary: Annotated[str, typer.Argument(help="Binary to discover tools from")],
) -> None:
    """(Stub) Discover tools from a binary's --help output."""
    console.print(f"[yellow]discover is not yet implemented.[/] Binary: {binary}")
    console.print("This will be available in a future version.")


def _print_banner(config: object) -> None:
    """Print a startup banner with server info."""
    from mcpforge.config import ForgeConfig

    assert isinstance(config, ForgeConfig)
    tool_names = [t.name for t in config.tools]

    banner = Table.grid(padding=1)
    banner.add_row("[bold cyan]MCPForge[/]", f"v{__version__}")
    banner.add_row("[bold]Server:[/]", config.forge.name)
    banner.add_row("[bold]Transport:[/]", config.server.transport.value)
    if config.server.transport == TransportType.http:
        banner.add_row("[bold]Endpoint:[/]", f"http://{config.server.host}:{config.server.port}")
    banner.add_row("[bold]Tools:[/]", ", ".join(tool_names) or "(none)")
    banner.add_row("[bold]Auth:[/]", config.auth.mode.value)

    console.print(Panel(banner, title="[bold]MCPForge Server[/]", border_style="cyan"))


if __name__ == "__main__":
    app()
