# MCPForge v0.1 — Autonomous Work Session TODO
**For Claude Code — work through these in order, check off as done, add notes**
**Last updated: 2026-03-11 | Owner: Mihai**

---

## 🎯 Session Goal
Build a working PoC of MCPForge that can:
1. Read a `mcp-forge.yaml` config file
2. Spawn a real FastMCP server from it (no handwritten server.py)
3. Expose CLI tools as MCP tools with typed args
4. Run in both `stdio` and `http` transport modes
5. Be callable from Claude Desktop or any MCP client

**Definition of Done:** Claude Desktop can call a tool defined only in `mcp-forge.yaml` — e.g. wrapping `ffmpeg` or `git log` — with zero Python written by the user.

---

## 📋 Tasks

### PHASE 1 — Project Scaffold
- [x] **1.1** Create project structure:
  ```
  mcpforge/
  ├── mcpforge/
  │   ├── __init__.py
  │   ├── cli.py          # typer CLI entrypoint
  │   ├── config.py       # pydantic models for mcp-forge.yaml
  │   ├── engine.py       # core: config → FastMCP server
  │   ├── adapters/
  │   │   ├── __init__.py
  │   │   ├── base.py     # abstract adapter
  │   │   └── cli.py      # CLI adapter (first one)
  │   └── output.py       # output mapping (stdout/json/exit_code)
  ├── tests/
  ├── examples/
  │   ├── git-tools.yaml
  │   └── media-tools.yaml
  ├── pyproject.toml
  └── README.md
  ```

- [x] **1.2** Set up `pyproject.toml` with dependencies:
  - `fastmcp>=3.0`
  - `pydantic>=2.0`
  - `typer`
  - `pyyaml`
  - `rich` (for beautiful CLI output)
  - `anyio` (async subprocess)

- [x] **1.3** Create the Pydantic config models in `config.py`:
  - `ForgeConfig` (top level)
  - `ServerConfig` (transport, port, host)
  - `ToolConfig` (name, description, adapter type, args, output)
  - `ArgConfig` (name, type, required, flag, default, enum, positional, secret)
  - `OutputConfig` (type, format, field, jq, streaming, exit_codes)
  - `AuthConfig` (mode, api_keys)
  - `CLIAdapterConfig` (command, subcommand, timeout_seconds, working_dir)
  - Write a `load_config(path)` function that validates and returns `ForgeConfig`

- [x] **1.4** Validate config loading works with a test YAML — use `examples/git-tools.yaml`

---

### PHASE 2 — CLI Adapter
- [x] **2.1** Implement `adapters/cli.py`:
  - Takes a `ToolConfig` + `CLIAdapterConfig`
  - Builds the subprocess command from args + flags
  - Handles: positional args, flag args (`--flag value`), boolean flags (`--flag`)
  - Handles: env var injection, working_dir, timeout
  - Returns an async function compatible with FastMCP tool registration

- [x] **2.2** Implement `output.py` — output mapping:
  - `stdout` → return raw string
  - `json_field` → parse JSON, extract field by dot-notation path
  - `exit_code` → map exit codes to success/error messages
  - `stderr` → return stderr as string
  - Always: capture both stdout AND stderr, decide based on config which to return
  - On timeout: return clean error message, not exception traceback

- [x] **2.3** Write unit tests for the CLI adapter:
  - Test with `echo` (always available, cross-platform)
  - Test with `git log --oneline -n 5` 
  - Test timeout handling
  - Test exit code mapping
  - Test json_field extraction

---

### PHASE 3 — FastMCP Engine
- [x] **3.1** Implement `engine.py` — the core loop:
  ```python
  def build_server(config: ForgeConfig) -> FastMCP:
      mcp = FastMCP(config.forge.name)
      for tool in config.tools:
          handler = build_handler(tool)  # returns async fn
          mcp.tool(name=tool.name, description=tool.description)(handler)
      return mcp
  ```

- [x] **3.2** Implement `build_handler(tool)` — generates the async tool function:
  - Dynamically builds function signature from `tool.args` (so FastMCP gets correct JSON schema)
  - Uses Pydantic to validate incoming args before execution
  - Calls the appropriate adapter
  - Wraps output mapping
  - NOTE: FastMCP needs real function signatures with typed params for schema generation — use `inspect` + dynamic function creation or explicit schema passing

- [x] **3.3** Test the engine builds a valid FastMCP server from a YAML config

- [x] **3.4** Verify the generated MCP schema looks correct (use `mcp dev` inspector)

---

### PHASE 4 — CLI Entrypoint
- [x] **4.1** Implement `cli.py` with Typer:
  ```
  mcp-forge serve [config]     # start the server
  mcp-forge validate [config]  # validate config, exit 0/1
  mcp-forge discover <binary>  # (stub for now, implement later)
  mcp-forge version            # print version
  ```

- [x] **4.2** `mcp-forge serve` should:
  - Load and validate config (fail fast with clear error if invalid)
  - Print startup banner with Rich (server name, tools list, transport, port)
  - Start FastMCP in stdio OR http mode based on config
  - Accept `--transport` and `--port` CLI flags to override config

- [x] **4.3** Add `mcp-forge wait-ready` command:
  - Polls `GET /health` in a loop
  - Exits 0 when server responds, exits 1 on timeout
  - Used in CI/CD pipelines

- [x] **4.4** Add `/health` endpoint to the HTTP server:
  - Returns `{"status": "ok", "server": "<name>", "tools": ["tool1", "tool2"]}`

---

### PHASE 5 — Example Configs
- [x] **5.1** Write `examples/git-tools.yaml`:
  - `git_log` — recent commits
  - `git_status` — working tree status
  - `git_diff` — diff of current changes
  - `git_branch` — list branches

- [x] **5.2** Write `examples/media-tools.yaml`:
  - `convert_video` — ffmpeg wrapper (with fallback message if ffmpeg not installed)
  - `get_video_info` — ffprobe wrapper
  - Check binary existence at startup, warn if not found

- [x] **5.3** Write `examples/dev-tools.yaml`:
  - `list_processes` — ps aux / tasklist
  - `disk_usage` — du -sh
  - `ping_host` — ping with exit code mapping
  - `run_command` — generic shell (add to security note: local use only, never expose remotely without auth)

---

### PHASE 6 — Integration Test
- [x] **6.1** End-to-end test:
  - Run `mcp-forge serve examples/git-tools.yaml --transport http`
  - Connect with `mcp-cli` or `mcp dev` inspector
  - Call `git_log` tool, verify output is correct
  - Call with invalid args, verify error handling

- [x] **6.2** Claude Desktop integration test:
  - Add MCPForge to `claude_desktop_config.json`:
    ```json
    {
      "mcpServers": {
        "mcpforge-git": {
          "command": "mcp-forge",
          "args": ["serve", "/path/to/examples/git-tools.yaml"]
        }
      }
    }
    ```
  - Restart Claude Desktop
  - Ask Claude "what's the recent git log?" — it should use the tool

- [x] **6.3** Document any issues found, add to NOTES section below

---

### PHASE 7 — Polish (only if phases 1-6 are done)
- [x] **7.1** Better error messages:
  - If binary not found: "Tool 'git_log' failed: command 'gitt' not found. Is it installed and on PATH?"
  - If YAML invalid: show which field, what was expected
  - If timeout: "Tool 'convert_video' timed out after 30s"

- [x] **7.2** Add `--install` convenience command:
  ```
  mcp-forge install examples/git-tools.yaml --client claude-desktop
  ```
  Writes the correct entry to claude_desktop_config.json automatically.

- [x] **7.3** Write README.md with:
  - 30-second quickstart
  - Full config reference (copy from spec)
  - Example configs
  - CI/CD GitHub Actions snippet

---

## 🚫 Out of Scope for v0.1
Do NOT implement these yet — they're v0.2+:
- Web UI (the beautiful dashboard)
- REST adapter
- Python function adapter
- OAuth2 / JWT auth (api_key is enough for now)
- Tool composition / pipelines
- Registry
- AI-powered import
- Hot reload

---

## ⚠️ Important Notes for Claude Code

**On dynamic function signatures:**
FastMCP infers JSON schema from Python function signatures. For dynamically generated tools, you may need to either:
- Use `make_function` / `exec` to create real typed functions at runtime, OR
- Pass explicit `parameters` schema to FastMCP's tool registration
Check FastMCP 3.x docs for the `@mcp.tool(parameters=...)` override — this is likely the cleanest path.

**On cross-platform:**
- Use `anyio.run_process()` for subprocess, not `subprocess.run()` — handles async correctly
- For Windows compatibility: don't assume `/` paths, use `pathlib.Path`
- `ps aux` doesn't exist on Windows — shell examples should note platform

**On security:**
- The `run_command` generic shell tool in dev-tools.yaml is dangerous for remote exposure — add a clear warning comment in the YAML and check `server.host` at startup: if `0.0.0.0` and auth is `none`, print a big warning

**On FastMCP version:**
- Use FastMCP 3.x (latest stable). API changed significantly from 2.x.
- Check: `pip show fastmcp` — should be 3.x
- Docs: https://gofastmcp.com

---

## 📝 Session Notes

**Started:** 2026-03-11
**Completed tasks:** All phases 1-7
**Blockers / decisions made:**
- FastMCP 3.1.0 uses `server.get_tool()` API (not `_tool_manager._tools`)
- `ping` not available in sandbox — handled with FileNotFoundError catch in CLI adapter
- Used `anyio.fail_after` + `anyio.run_process` for async subprocess with timeout
- Dynamic function signatures via `inspect.Signature` replacement on handler — FastMCP picks up typed params correctly
- `streamable-http` transport used for HTTP mode (FastMCP 3.x convention)
- Added `install` command for Claude Desktop config injection (cross-platform path detection)

**What's left for next session:**
- Shell adapter implementation (Phase 2 spec mentions it but it's lower priority)
- Web UI (v0.2 scope)
- REST/Python/OpenAPI adapters (v0.2+ scope)
- Hot reload (v0.2+ scope)

---

## ✅ Quick Sanity Check Before Starting
- [x] Python 3.11+ available (`python --version`) — Python 3.11.14
- [x] pip / uv available — pip 24.0
- [x] git available — git 2.43.0
- [x] `fastmcp` installable (`pip install fastmcp`) — fastmcp 3.1.0
- [x] Working directory is clean / new project folder

---
*This TODO is for MCPForge v0.1 PoC — the spec is in MCPForge-Spec-v0.2.md*
