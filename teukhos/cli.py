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

def _version_callback(value: bool) -> None:
    if value:
        print(f"Teukhos v{__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="teukhos",
    help=(
        f"Teukhos v{__version__} -- Spawn MCP servers from declarative YAML configuration.\n\n"
        "You describe the tool. Teukhos forges it."
    ),
    no_args_is_help=True,
)
console = Console(stderr=True)


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", help="Show version and exit.", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Teukhos -- Spawn MCP servers from declarative YAML configuration."""

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
    console.print(f"[dim]Loading config: {config.resolve()}[/]")

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

    if forge_config.server.transport == TransportType.http:
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware

        from teukhos.auth import AuthMiddleware

        middleware: list[Middleware] = []

        # Wire auth middleware if keys are configured
        if bundle.resolved_auth_keys:
            middleware.append(
                Middleware(AuthMiddleware, api_keys=bundle.resolved_auth_keys)
            )

        # Wire CORS middleware if origins are configured
        if bundle.cors_origins:
            middleware.append(
                Middleware(
                    CORSMiddleware,
                    allow_origins=bundle.cors_origins,
                    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                    allow_headers=[
                        "mcp-protocol-version",
                        "mcp-session-id",
                        "Authorization",
                        "Content-Type",
                    ],
                    expose_headers=["mcp-session-id"],
                )
            )

        mcp.run(
            transport="streamable-http",
            host=forge_config.server.host,
            port=forge_config.server.port,
            middleware=middleware or None,
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
    console.print(f"[dim]Validating: {config.resolve()}[/]")

    try:
        forge_config = load_config(config)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Validation error:[/] {e}")
        raise typer.Exit(1)

    console.print(
        f"[bold green]Valid![/] Server '{forge_config.forge.name}' "
        f"with {len(forge_config.tools)} tool(s)."
    )

    table = Table(title="Tools")
    table.add_column("Name", style="cyan")
    table.add_column("Adapter", style="magenta")
    table.add_column("Description")
    for tool in forge_config.tools:
        table.add_row(tool.name, tool.adapter, tool.description)
    console.print(table)

    console.print(
        f"\n[dim]Transport: {forge_config.server.transport.value} | "
        f"Auth: {forge_config.auth.mode.value}[/]"
    )


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
    console.print(f"[dim]Polling {url} (timeout: {timeout}s)...[/]")

    while time.monotonic() - start < timeout:
        try:
            resp = httpx.get(url, timeout=2)
            if resp.status_code == 200:
                elapsed = time.monotonic() - start
                console.print(f"[bold green]Server is ready![/] (responded in {elapsed:.1f}s)")
                raise typer.Exit(0)
        except httpx.ConnectError:
            pass
        time.sleep(1)

    console.print(f"[bold red]Timeout:[/] Server at {url} not ready after {timeout}s")
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
    dest: Annotated[
        Optional[str], typer.Option("--dest", help="Write to an arbitrary JSON config file path")
    ] = None,
    config_key: Annotated[
        str, typer.Option("--config-key", help="JSON key for server entries (default: mcpServers)")
    ] = "mcpServers",
) -> None:
    """Install a Teukhos server into MCP client(s).

    By default, discovers installed clients and prompts you to choose.
    Use --client to target a specific one, or --all for all detected clients.
    Use --url to configure HTTP transport (for remote servers).
    Use --dest to write directly to any JSON file (bypasses client detection).
    """
    from teukhos.installers import discover_clients, get_all_installers, get_installer
    from teukhos.installers.base import InstallScope

    scope = InstallScope.project if project else InstallScope.global_
    transport_mode = "http" if url else "stdio"

    # --dest mode: write directly to an arbitrary JSON file
    if dest:
        from teukhos.installers.base import (
            atomic_write_json,
            merge_mcp_entry,
            read_json_config,
        )
        import shutil

        dest_path = Path(dest).resolve()
        console.print(f"[dim]Target: {dest_path} (config-key: {config_key})[/]")

        # Resolve server name
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
            console.print(f"[dim]Config: {config_path}[/]")
        else:
            config_path = _resolve_config(config)
            if config_path.exists():
                try:
                    forge_config = load_config(config_path)
                    server_name = f"teukhos-{forge_config.forge.name}"
                except Exception:
                    server_name = "teukhos-remote"
            else:
                server_name = "teukhos-remote"

        # Build entry
        existing = read_json_config(dest_path)
        if url:
            entry: dict = {"url": url}
            if config_key == "servers":
                entry["type"] = "http"
            if key and key != "env:TEUKHOS_API_KEY":
                if key.startswith("env:"):
                    env_var = key[4:]
                    entry["headers"] = {"Authorization": f"Bearer ${{{env_var}}}"}
                else:
                    entry["headers"] = {"Authorization": f"Bearer {key}"}
            elif key == "env:TEUKHOS_API_KEY":
                entry["headers"] = {"Authorization": "Bearer ${TEUKHOS_API_KEY}"}
        else:
            teukhos_bin = shutil.which("teukhos") or "teukhos"
            entry = {
                "command": teukhos_bin,
                "args": ["serve", str(config_path)],
            }
            if config_key == "servers":
                entry["type"] = "stdio"

        merge_mcp_entry(existing, server_name, entry, key=config_key)
        atomic_write_json(dest_path, existing)

        console.print()
        console.print(f"[bold green]Installed![/] MCP server registered successfully.")
        console.print(f"  Server name:  {server_name}")
        console.print(f"  Transport:    {transport_mode}")
        console.print(f"  Config key:   {config_key}")
        console.print(f"  Written to:   {dest_path}")
        if url:
            console.print(f"  URL:          {url}")
        return

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
        console.print(f"[dim]Installing for {len(targets)} detected client(s)...[/]")
    else:
        detected = discover_clients()
        if not detected:
            all_inst = get_all_installers()
            console.print("[yellow]No MCP clients auto-detected.[/]")
            console.print("Available clients:")
            for inst in all_inst:
                console.print(f"  {inst.slug:20s} {inst.name}")
            console.print("\nUse --client <slug> to install for a specific client.")
            console.print("Use --dest <path> to install to any JSON config file.")
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
        console.print(f"[dim]Config: {config_path}[/]")
    else:
        # HTTP mode -- server_name derived from URL or config if available
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
    console.print()
    for inst in targets:
        try:
            if url:
                inst.install_http(server_name, url, key, scope=scope)
            else:
                inst.install_stdio(server_name, config_path, scope=scope)
            effective_scope = inst._effective_scope(scope)
            target_path = inst.config_path(effective_scope)
            console.print(f"[bold green]Installed![/] {inst.name}")
            console.print(f"  Server name:  {server_name}")
            console.print(f"  Transport:    {transport_mode}")
            console.print(f"  Scope:        {effective_scope.value}")
            console.print(f"  Config file:  {target_path}")
            if url:
                console.print(f"  URL:          {url}")
            console.print()
        except Exception as e:
            console.print(f"[bold red]Error installing for {inst.name}:[/] {e}\n")

    console.print("[dim]Restart your client(s) to pick up the changes.[/]")


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
        console.print(f"[dim]Removing from {len(targets)} detected client(s)...[/]")
    else:
        console.print("[bold red]Error:[/] Specify --client <slug> or --all.")
        raise typer.Exit(1)

    console.print()
    for inst in targets:
        try:
            effective_scope = inst._effective_scope(scope)
            target_path = inst.config_path(effective_scope)
            inst.uninstall(server_name, scope=scope)
            console.print(f"[bold green]Removed![/] '{server_name}' from {inst.name}")
            console.print(f"  Scope:        {effective_scope.value}")
            console.print(f"  Config file:  {target_path}")
            console.print()
        except Exception as e:
            console.print(f"[bold red]Error removing from {inst.name}:[/] {e}\n")

    console.print("[dim]Restart your client(s) to pick up the changes.[/]")


@app.command()
def clients() -> None:
    """List all supported MCP clients and their detection status."""
    from teukhos.installers import get_all_installers
    from teukhos.installers.base import InstallScope

    all_inst = get_all_installers()
    detected_count = sum(1 for inst in all_inst if inst.detect())

    console.print(
        f"[bold]Teukhos v{__version__}[/] -- "
        f"{len(all_inst)} supported clients, "
        f"{detected_count} detected on this system.\n"
    )

    home = Path.home()
    for inst in all_inst:
        detected = inst.detect()
        marker = "[green]Yes[/]" if detected else "[dim]No[/]"
        scopes = ", ".join(s.value for s in inst.supported_scopes)
        full_path = inst.config_path(InstallScope.global_)
        try:
            short_path = "~/" + str(full_path.relative_to(home)).replace("\\", "/")
        except ValueError:
            short_path = str(full_path)

        name_style = "bold cyan" if detected else "dim"
        console.print(f"  [{name_style}]{inst.name}[/] ({inst.slug})  {marker}")
        console.print(f"    Scopes: {scopes}  |  Config: {short_path}")

    console.print(
        f"\n[dim]Use 'teukhos install <config> --client <slug>' to register with a client.[/]"
    )


@app.command()
def discover(
    binary: Annotated[str, typer.Argument(help="Binary to discover tools from")],
) -> None:
    """(Coming soon) Auto-generate a teukhos.yaml from a binary's --help output."""
    console.print(f"[yellow]discover is not yet implemented.[/] Binary: {binary}")
    console.print("This will be available in a future version with AI-powered tool import.")


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
