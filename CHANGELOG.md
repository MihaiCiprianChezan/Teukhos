# Changelog

All notable changes to Teukhos are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security
- **API-key auth bypass via the `Host` header.** A request with e.g. `Host: a?` reached `/mcp` without a key, because the middleware matched `request.url.path`, which Starlette rebuilds from `Host`. Auth now matches the routed path and denies by default; only `/health` is public.
- **Auth failed open.** `auth.mode: api_key` with no resolvable key (env var unset) served without authentication. `serve` over HTTP now refuses to start.
- **Argument injection.** LLM-supplied positional and flag-less values starting with `-` are rejected (e.g. `--output=...` into git), including Unicode look-alikes that Windows converts to `-`. Enum values and configured defaults are exempt.
- **`enum` is enforced** and published in the tool schema; it was documented but ignored. Values (and the default) are coerced to the arg type; an enum on a boolean arg, YAML booleans or non-integer numbers in an integer enum, and a default outside the enum are config errors.
- **`secret` works.** A secret arg with a default is hidden from the tool schema and a string default is redacted from tool output (before truncation, so a cut can't expose part of it). Previously the flag did nothing and defaults were published in `tools/list`.
- **Origin check.** Browser requests whose `Origin` isn't in `cors_origins` get 403 (DNS rebinding, websites calling a local server).
- **Windows:** `.cmd`/`.bat` commands reject arguments containing `cmd.exe` metacharacters or argument separators (command and argument injection); bare command names are no longer resolved from the server's current directory (binary planting), and tool processes inherit that setting; MSYS/Cygwin tools get `noglob`.
- **Codex installer:** `forge.name` could inject extra `[mcp_servers.*]` tables into `~/.codex/config.toml`; keys are now quoted and values escaped.
- `examples/database-tools.yaml`: `sqlite_query` runs with `-safe -readonly`, `sqlite_tables`/`sqlite_schema` pin their `query` arg with `enum` (it accepted `.shell`), and `pg_query` is removed (psql runs backslash meta-commands from `-c` and has no safe mode).
- `serve` warns for any non-loopback bind without auth (was `0.0.0.0` only), and refuses to start over HTTP with `cors_origins: ["*"]` and no auth (`*` turns the Origin check off).

### Added
- `cli.max_output_bytes` (default 1 MB): stdout/stderr beyond it are truncated with a marker. Output is captured in temp files, so memory stays bounded. A `json_field` tool whose JSON exceeds the limit returns an error that says to raise it.
- The `/health` endpoint is registered. It was advertised but returned 404, so `wait-ready` and the Docker `HEALTHCHECK` always timed out.

### Fixed
- Codex installer wrote invalid TOML on Windows (unescaped backslashes), and reinstall/uninstall left `args = [...]` lines behind that corrupted other entries. Sections are now removed up to the next header (comments introducing the next table are kept), the result is checked with `tomllib` before an atomic write, and a config broken by an older version is repaired on reinstall. Stray `args = [...]` lines that an older version left inside another server's table must be removed by hand.
- Codex HTTP entries use `bearer_token_env_var` / `http_headers`, the keys Codex reads; the old `[headers]` table was ignored, so no auth header was sent.
- `cli.env` adds to the server's environment as documented instead of replacing it (children lost `PATH`/`SYSTEMROOT`).
- Windows: `npx`, `npm`, `az` and other `.cmd` shims work as bare command names (they failed with "not found"). The shim is only a fallback when no `.exe` is found, so existing commands resolve as before.
- Windows: `timeout_seconds` is enforced even when a grandchild process keeps the output open.
- A missing `working_dir` is reported as such instead of "command not found" (or an uncaught exception); `~` is expanded. Other `OSError`s and rejected arguments return a tool error and are logged with traceback.
- `output.type: exit_code` reports timeouts and missing binaries instead of "Failed with exit code -1".
- CORS middleware runs before auth, so browser preflights get through.
- Config files are read as bytes, so UTF-8 with BOM and UTF-16 (common on Windows) load correctly; a BOM used to silently drop the first section.
- Rich markup in names, paths or errors (e.g. `tools[/bold]`) no longer crashes `install` or `validate`, or garbles `discover` errors.
- JSON `uninstall` no longer creates a config file for a client that has none; installs write through a symlink whose target exists (dangling links are replaced); an unresolvable `env:` key for a client without `${VAR}` support is an error instead of writing `Bearer env:VAR`.
- **OpenCode installer** wrote `mcpServers` entries, which OpenCode ignores. It now writes OpenCode's format: the `mcp` key, `{type: "local", command: [...]}`, and `{type: "remote", url, oauth: false, headers}` with `{env:VAR}` substitution.
- **Claude Desktop installer:** `install --url` wrote a `url` entry that Claude Desktop skips (and then removes from the file); it now fails with a clear message. The Linux config path is `~/.config/Claude` (was lowercase `claude`), honouring `XDG_CONFIG_HOME`; Windows uses `%APPDATA%`.
- **fastmcp 4.x:** CORS preflights allow the `mcp-method`/`mcp-name` headers that MCP 2026-07-28 clients send, so browser clients work with `cors_origins`. Verified against fastmcp 3.1.1, 4.0.0 and 4.1.0.
- `examples/archive-tools.yaml`: `zip_create` and `zip_list` were Python syntax errors (a folded YAML block joined the lines), and `file_checksum` never finished (it reopened the file for every read).
- The `serve` banner shows how many API keys resolved, not just how many are configured.
- Tool results are sent once as text instead of also as a duplicate `structuredContent`; `json_field` objects keep non-ASCII text unescaped.

### Changed
- Unknown config keys are rejected, so typos fail `teukhos validate`.
- `AuthMiddleware(protected_paths=...)` is replaced by `public_paths` (default `["/health"]`); an empty key list denies all requests.
- Codex entries no longer include a `type` key (Codex ignores it); `config.toml` is written with mode 0600, existing files included, like the JSON installers.
- Config files must be UTF-8 (BOM optional) or UTF-16; ANSI/cp1252 files with non-ASCII text must be re-saved as UTF-8.

---

## [0.3.9] — 2026-03-18

### Added
- **`--exec-timeout` / `-e` flag** for `teukhos discover` — sets `timeout_seconds` in generated YAML independently from discovery timeout
- Discovery (`--timeout`) and execution (`--exec-timeout`) timeouts are now separate concerns:
  `--timeout` controls how long each `--help` subprocess can take during discovery,
  `--exec-timeout` controls how long generated tools are allowed to run

### Changed
- `--timeout` now only affects discovery `--help` calls (no longer also sets `timeout_seconds` in generated YAML)

---

## [0.3.8] — 2026-03-18

### Fixed
- Leaf-command description extraction no longer picks up `Usage:` lines — uses shared `_extract_description()` helper
- `--timeout` now controls discovery subprocess calls too, not just the generated YAML `timeout_seconds`
- `--timeout 0` no longer silently falls back to default (proper `is not None` check)
- Duplicate commands in `parse_commands()` when CLIs list the same command in multiple sections (e.g. gh)
- README recipe section clarified: default output is `<binary-name>.yaml`, not `teukhos.yaml`

### Added
- 28 unit tests for `teukhos/discover.py` — covers `_extract_description`, `parse_commands`, `parse_options`, `parse_positional_args`, and `generate_yaml`

### Changed
- Extracted `_extract_description()` as a shared helper, replacing duplicated logic in `discover_binary()`

---

## [0.3.7] — 2026-03-18

### Added
- **`teukhos discover <binary>`** — auto-generate `teukhos.yaml` configs by recursively parsing `--help` output
  (contributed by [@exalsch](https://github.com/exalsch))
- Supports GNU-style, .NET System.CommandLine, Azure CLI, and gh/cobra help formats
- `--max-depth` and `--filter` options to scope discovery for large CLIs
- `--dry-run` for syntax-highlighted YAML preview without writing a file
- `--timeout` option for slow CLI tools (e.g. COM-based OutlookCLI)
- Python reserved keyword collision handling (`--from` becomes `from_value`)

### Fixed
- Unused `traceback` import removed from `discover.py`
- `_PYTHON_RESERVED` comment corrected (was "keywords and builtins", only had keywords)
- Top-level description extraction no longer picks up `Usage:` lines
- `--timeout 0` no longer silently dropped in generated YAML
- `OSError` handling added for file write in discover command
- Help text for `--output` option corrected to match actual default filename

---

## [0.3.6] — 2026-03-17

### Changed
- **Cross-platform example configs** — `dev-tools.yaml`, `network-tools.yaml`, and `archive-tools.yaml`
  rewritten to work on Windows, Linux, and macOS without OS-specific variants.
  Uses Python stdlib (`shutil`, `socket`, `ssl`, `zipfile`, `hashlib`, `urllib`)
  to replace OS-specific CLI tools (`ps`, `du`, `dig`, `whois`, `sha256sum`, `zip`/`unzip`, etc.)
- Tools that differ per OS (`ping`, `traceroute`, `list_processes`) now auto-detect via `platform.system()`
- `run_command` tool uses Python `subprocess.run(shell=True)` — automatically picks the system shell

### Added
- **Comprehensive integration test suite** (`tests/test_all_servers.py`) — 62 tests covering
  all 20 MCP servers (10 stdio + 10 HTTP): ping, tool listing, schema validation,
  concurrent pings, rapid sequential pings, cross-transport comparison
- **Ping health check tool** added to all 10 example configs — `python -c "print('<name> v1.0.0: pong')"`
  pattern enables fast server health verification
- HTTP server start/stop scripts for dev testing (`scripts/start-http-servers.ps1`, `scripts/stop-http-servers.ps1`)

### Fixed
- Normalized em dashes to hyphens in ping tool descriptions for consistent output parsing

---

## [0.3.3] — 2026-03-17

### Added
- **Auth middleware wired into FastMCP** — `AuthMiddleware` now protects HTTP `/mcp` endpoint via `mcp.run(middleware=[...])`. Bearer token validation is fully functional for HTTP transport.
- **CORS middleware wired into FastMCP** — `cors_origins` config option now applies Starlette `CORSMiddleware` with MCP-specific headers (`mcp-protocol-version`, `mcp-session-id`, `Authorization`).

### Changed
- **Codex installer rewritten for TOML** — Codex uses `~/.codex/config.toml` (not JSON), now handled correctly with `[mcp_servers.<name>]` table format
- **Auggie renamed to Augment Code** — slug changed from `auggie` to `augment`, path corrected to `~/.augment/settings.json`
- Gemini CLI now supports project scope (`.gemini/settings.json`)
- Codex, CodeBuddy, and OpenCode now support project scope
- Cline changed to global-only (no separate project config)

### Fixed
- `__version__` now reads from `pyproject.toml` via `importlib.metadata` — single source of truth
- GitHub Copilot global config path corrected to `%APPDATA%/Code/User/mcp.json` on Windows
- **Cline** path corrected to VS Code `globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- **Roo Code** global path corrected to VS Code `globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`, project path to `.roo/mcp.json`
- **Continue.dev** global path corrected to `~/.continue/mcp.json`, project to `.continue/mcpServers/mcp.json`
- **Kiro** paths corrected to `~/.kiro/settings/mcp.json` (subfolder)
- **CodeBuddy** path corrected to `~/.codebuddy/.mcp.json` (dot prefix)
- **OpenCode** path corrected to `~/.config/opencode/opencode.json`

---

## [0.3.0] — 2026-03-16

### Added
- **Multi-client installer system** — plugin/strategy pattern with 15 supported MCP clients:
  Claude Desktop, Claude Code, Cursor, GitHub Copilot, Gemini CLI, Codex,
  Windsurf, Cline, Roo Code, Continue.dev, Kiro, Auggie, CodeBuddy, OpenCode, Trae
- **`teukhos install`** rewritten — auto-detect clients, `--client`, `--all`, `--project`,
  `--url` (HTTP), `--key` (API key), `--dest` (arbitrary JSON path), `--config-key`
- **`teukhos uninstall`** — remove server registrations from client configs
- **`teukhos clients`** — list all supported clients with detection status and config paths
- **`--dest` custom path install** — write MCP config to any JSON file, bypassing client detection
- **`--config-key`** option — choose `mcpServers` (default) or `servers` (GitHub Copilot format)
- **`env:` prefix API key resolution** — `"env:TEUKHOS_API_KEY"` reads from environment,
  plain strings used as literals. Default: `env:TEUKHOS_API_KEY`
- **`resolve_key()`** utility in `teukhos/auth.py` for env-var-or-literal key resolution
- **`AuthMiddleware`** — Bearer token validation middleware for HTTP transport
- **`ServerBundle`** dataclass — `build_server()` now returns bundle with resolved auth keys and CORS config
- **`cors_origins`** config option for HTTP transport CORS headers
- **Improved HTTP startup banner** — shows endpoint, health URL, auth status, and connect hint
- **Project-level install scope** — `--project` writes to `.cursor/mcp.json`, `.claude/settings.json`, etc.
  in current directory. Silently falls back to global for clients that don't support project scope
- **Atomic JSON writes** with backup (`.teukhos-backup`) for safe config file modifications
- Example config: `examples/remote-server.yaml`
- Architecture diagram: `docs/images/how-it-works.svg`
- Full README rewrite with recipes, deployment guide, and supported clients table

### Changed
- `build_server()` returns `ServerBundle` instead of raw `FastMCP` instance
- `install` command no longer hardcoded to Claude Desktop — uses installer plugin system
- Version bumped to 0.3.0 to mark multi-client and HTTP transport milestone

---

## [0.2.0] — 2026-03-15

### Changed
- **Project renamed from MCPForge to Teukhos** — unique name, clean namespace
  across PyPI, npm, GitHub, and all major registries
- CLI command changed from `mcp-forge` to `teukhos`
- Default config filename changed from `mcp-forge.yaml` to `teukhos.yaml`
- Legacy `mcp-forge.yaml` still accepted automatically with a deprecation note
- Package name on PyPI changed from `mcpforge` to `teukhos`
- All internal imports updated from `mcpforge.*` to `teukhos.*`
- `ForgeInfo.name` default updated to `teukhos-server`
- `install` command now registers as `teukhos-<name>` in Claude Desktop config
- Version bumped to 0.2.0 to mark the identity change cleanly

### Added
- `httpx` added as an explicit dependency (was implicit via fastmcp)
- Backward-compatible config file resolution (`_resolve_config` in CLI)
- `[tool.hatch.build.targets.wheel]` section in `pyproject.toml`
- Project URLs (Homepage, Repository, Issues) in `pyproject.toml`
- PyPI classifiers
- GitHub Actions CI workflow (`.github/workflows/ci.yml`)
- This CHANGELOG

### Fixed
- Boolean arg handling: cleaned up redundant condition in `_build_command`

---

## [0.1.0] — 2026-03-11

### Added
- Initial working PoC under the name MCPForge
- Pydantic config models for `mcp-forge.yaml`
- `cli` adapter with typed arg mapping (flags, positional, boolean)
- Output mapping: `stdout`, `stderr`, `json_field`, `exit_code`
- FastMCP server generation at runtime with dynamic function signatures
- `stdio` and `http` (streamable-http) transports
- `api_key` auth mode
- `serve`, `validate`, `version`, `wait-ready`, `install`, `discover` CLI commands
- Rich startup banner
- Security warning for unauthenticated 0.0.0.0 bindings
- Health endpoint `/health`
- Example configs: `git-tools.yaml`, `dev-tools.yaml`, `media-tools.yaml`
- Full test suite: unit + integration tests
- Claude Desktop integration via `install` command
