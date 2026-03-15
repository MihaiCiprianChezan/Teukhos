"""Teukhos CLI — Typer-based command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from teukhos import __version__
from teukhos.config import TransportType, load_config

app = typer.Typer(
    name="teukhos",
    help=(
        "Teukhos — Spawn MCP servers from declarative YAML configuration.\n\n"
        "In Homer's Greek, τεῦχος meant a crafted implement forged with purpose.\n"
        "You describe the tool. Teukhos forges it."
    ),
    no_args_is_help=True,
)
console = Console()

# Accept both the new teukhos.yaml and the legacy mcp-forge.yaml names
DEFAULT_CONFIG = "teukhos.yaml"
LEGACY_CONFIG = "mcp-forge.yaml"


def _resolve_config(path: Path) -> Path:
    """Resolve config path, falling back to legacy name if needed."""
    if path.exists():
        return path
    # Auto-fallback: if teukhos.yaml not found, try mcp-forge.yaml
    if path.name == DEFAULT_CONFIG:
        legacy = path.parent / LEGACY_CONFIG
        if legacy.exists():
            console.print(
                f"[dim]Note: Using legacy config name '{LEGACY_CONFIG}'. "
                f"Consider renaming to '{DEFAULT_CONFIG}'.[/]"
            )
            return legacy
    return path


@app.command()
def serve(
    config: Annotated[
        Path, typer.Argument(help="Path to teukhos.yaml config file")
    ] = Path(DEFAULT_CONFIG),
    transport: Annotated[
        Optional[str], typer.Option("--transport", "-t", help="Override transport (stdio/http)")
    ] = None,
    port: Annotated[
        Optional[int], typer.Option("--port", "-p", help="Override HTTP port")
    ] = None,
) -> None:
    """Start the Teukhos MCP server."""
    config = _resolve_config(config)

    try:
        forge_config = load_config(config)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Config validation error:[/] {e}")
        raise typer.Exit(1)

    if transport:
        try:
            forge_config.server.transport = TransportType(transport)
        except ValueError:
            console.print(
                f"[bold red]Error:[/] Invalid transport '{transport}'. Use 'stdio' or 'http'."
            )
            raise typer.Exit(1)
    if port:
        forge_config.server.port = port

    # Check binaries
    from teukhos.adapters.cli import CLIAdapter

    for tool in forge_config.tools:
        if tool.adapter == "cli" and tool.cli:
            adapter = CLIAdapter(tool.cli, tool.args)
            warning = adapter.check_binary()
            if warning:
                console.print(f"[bold yellow]Warning:[/] Tool '{tool.name}': {warning}")

    # Security warning for exposed unauthenticated servers
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

    _print_banner(forge_config)

    from teukhos.engine import build_server

    bundle = build_server(forge_config)
    mcp = bundle.mcp

    # TODO: wire bundle.resolved_auth_keys and bundle.cors_origins into FastMCP middleware
    # when FastMCP 3.x exposes a clean middleware injection API.

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
        Path, typer.Argument(help="Path to teukhos.yaml config file")
    ] = Path(DEFAULT_CONFIG),
) -> None:
    """Validate a teukhos.yaml config file. Exits 0 if valid, 1 if not."""
    config = _resolve_config(config)

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
    """Print Teukhos version."""
    console.print(f"Teukhos v{__version__}")


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
                console.print("[bold green]Server is ready![/]")
                raise typer.Exit(0)
        except httpx.ConnectError:
            pass
        time.sleep(1)

    console.print(f"[bold red]Timeout:[/] Server not ready after {timeout}s")
    raise typer.Exit(1)


@app.command()
def install(
    config: Annotated[
        Path, typer.Argument(help="Path to teukhos.yaml config file")
    ] = Path(DEFAULT_CONFIG),
    client: Annotated[
        Optional[str], typer.Option("--client", "-c", help="Target client by slug")
    ] = None,
    all_clients: Annotated[
        bool, typer.Option("--all", help="Install for all detected clients")
    ] = False,
    project: Annotated[
        bool, typer.Option("--project", help="Use project-level config instead of global")
    ] = False,
    url: Annotated[
        Optional[str], typer.Option("--url", help="Remote server URL (enables HTTP mode)")
    ] = None,
    key: Annotated[
        str, typer.Option("--key", help="API key for HTTP mode")
    ] = "env:TEUKHOS_API_KEY",
) -> None:
    """Install a Teukhos server into MCP client(s).

    By default, discovers installed clients and prompts you to choose.
    Use --client to target a specific one, or --all for all detected clients.
    Use --url to configure HTTP transport (for remote servers).
    """
    from teukhos.installers import discover_clients, get_all_installers, get_installer
    from teukhos.installers.base import InstallScope

    scope = InstallScope.project if project else InstallScope.global_

    # Determine target installers
    if client:
        inst = get_installer(client)
        if inst is None:
            console.print(f"[bold red]Error:[/] Unknown client '{client}'.")
            console.print("Run 'teukhos clients' to see available clients.")
            raise typer.Exit(1)
        targets = [inst]
    elif all_clients:
        targets = discover_clients()
        if not targets:
            console.print("[yellow]No MCP clients detected on this system.[/]")
            raise typer.Exit(0)
    else:
        detected = discover_clients()
        if not detected:
            all_inst = get_all_installers()
            console.print("[yellow]No MCP clients auto-detected.[/]")
            console.print("Available clients:")
            for inst in all_inst:
                console.print(f"  {inst.slug:20s} {inst.name}")
            console.print("\nUse --client <slug> to install for a specific client.")
            raise typer.Exit(0)

        console.print("[bold]Detected MCP clients:[/]")
        for i, inst in enumerate(detected, 1):
            console.print(f"  {i}. {inst.name} ({inst.slug})")

        choice = typer.prompt(
            "Install for which client? (number, 'all', or 'q' to quit)",
            default="1",
        )
        if choice.lower() == "q":
            raise typer.Exit(0)
        if choice.lower() == "all":
            targets = detected
        else:
            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(detected):
                    raise ValueError
                targets = [detected[idx]]
            except ValueError:
                console.print("[bold red]Invalid choice.[/]")
                raise typer.Exit(1)

    # Resolve config for stdio mode
    if not url:
        config_path = _resolve_config(config).resolve()
        if not config_path.exists():
            console.print(f"[bold red]Error:[/] Config file not found: {config_path}")
            raise typer.Exit(1)
        try:
            forge_config = load_config(config_path)
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
            raise typer.Exit(1)
        server_name = f"teukhos-{forge_config.forge.name}"
    else:
        # HTTP mode — server_name derived from URL or config if available
        config_path = _resolve_config(config)
        if config_path.exists():
            try:
                forge_config = load_config(config_path)
                server_name = f"teukhos-{forge_config.forge.name}"
            except Exception:
                server_name = "teukhos-remote"
        else:
            server_name = "teukhos-remote"

    # Install
    for inst in targets:
        try:
            if url:
                inst.install_http(server_name, url, key, scope=scope)
            else:
                inst.install_stdio(server_name, config_path, scope=scope)
            effective_scope = inst._effective_scope(scope)
            console.print(
                f"[bold green]Installed![/] '{server_name}' → {inst.name} "
                f"({effective_scope.value}: {inst.config_path(effective_scope)})"
            )
        except Exception as e:
            console.print(f"[bold red]Error installing for {inst.name}:[/] {e}")

    if not url:
        console.print("\n[dim]Restart your client(s) to pick up the changes.[/]")


@app.command()
def uninstall(
    server_name: Annotated[
        str, typer.Argument(help="Server name to remove (e.g., teukhos-git-tools)")
    ],
    client: Annotated[
        Optional[str], typer.Option("--client", "-c", help="Target client by slug")
    ] = None,
    all_clients: Annotated[
        bool, typer.Option("--all", help="Remove from all detected clients")
    ] = False,
    project: Annotated[
        bool, typer.Option("--project", help="Target project-level config")
    ] = False,
) -> None:
    """Remove a Teukhos server from MCP client(s)."""
    from teukhos.installers import discover_clients, get_installer
    from teukhos.installers.base import InstallScope

    scope = InstallScope.project if project else InstallScope.global_

    if client:
        inst = get_installer(client)
        if inst is None:
            console.print(f"[bold red]Error:[/] Unknown client '{client}'.")
            raise typer.Exit(1)
        targets = [inst]
    elif all_clients:
        targets = discover_clients()
        if not targets:
            console.print("[yellow]No MCP clients detected.[/]")
            raise typer.Exit(0)
    else:
        console.print("[bold red]Error:[/] Specify --client <slug> or --all.")
        raise typer.Exit(1)

    for inst in targets:
        try:
            inst.uninstall(server_name, scope=scope)
            console.print(f"[bold green]Removed![/] '{server_name}' from {inst.name}")
        except Exception as e:
            console.print(f"[bold red]Error removing from {inst.name}:[/] {e}")


@app.command()
def clients() -> None:
    """List all supported MCP clients and their detection status."""
    from teukhos.installers import get_all_installers
    from teukhos.installers.base import InstallScope

    table = Table(title="Supported MCP Clients")
    table.add_column("Client", style="cyan")
    table.add_column("Slug", style="magenta")
    table.add_column("Detected", justify="center")
    table.add_column("Scopes")
    table.add_column("Global Config Path", style="dim")

    for inst in get_all_installers():
        detected = "[green]Yes[/]" if inst.detect() else "[dim]No[/]"
        scopes = ", ".join(s.value for s in inst.supported_scopes)
        config_path = str(inst.config_path(InstallScope.global_))
        table.add_row(inst.name, inst.slug, detected, scopes, config_path)

    console.print(table)


@app.command()
def discover(
    binary: Annotated[str, typer.Argument(help="Binary to discover tools from")],
) -> None:
    """(Coming in v0.3) Auto-generate a teukhos.yaml from a binary's --help output."""
    console.print(f"[yellow]discover is not yet implemented.[/] Binary: {binary}")
    console.print("This will be available in v0.3 with AI-powered tool import.")


def _print_banner(config: object) -> None:
    """Print a startup banner with server info."""
    from teukhos.config import ForgeConfig

    assert isinstance(config, ForgeConfig)
    tool_names = [t.name for t in config.tools]

    banner = Table.grid(padding=1)
    banner.add_row("[bold cyan]Teukhos[/]", f"v{__version__}")
    banner.add_row("[bold]Server:[/]", config.forge.name)
    banner.add_row("[bold]Transport:[/]", config.server.transport.value)
    if config.server.transport == TransportType.http:
        host = config.server.host
        port = config.server.port
        banner.add_row("[bold]Endpoint:[/]", f"http://{host}:{port}/mcp")
        banner.add_row("[bold]Health:[/]", f"http://{host}:{port}/health")
    banner.add_row("[bold]Tools:[/]", ", ".join(tool_names) or "(none)")

    # Auth info
    auth_mode = config.auth.mode.value
    if auth_mode == "api_key":
        key_count = len(config.auth.api_keys)
        banner.add_row("[bold]Auth:[/]", f"api_key ({key_count} key(s) configured)")
    else:
        banner.add_row("[bold]Auth:[/]", auth_mode)

    # Connection hint for HTTP
    if config.server.transport == TransportType.http:
        banner.add_row("", "")
        banner.add_row("[bold]Connect:[/]", f"teukhos install --url http://HOST:{config.server.port}/mcp")

    console.print(Panel(banner, title="[bold]Teukhos MCP Server[/]", border_style="cyan"))


if __name__ == "__main__":
    app()
