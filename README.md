# MCPForge — Architecture & Feature Spec v0.2
**Spawn production-grade MCP servers from config**

---

## 0. The Problem Statement

The MCP ecosystem has a critical gap:

| What exists | What's missing |
|---|---|
| Raw FastMCP (write Python) | **Config-as-code → running MCP server** |
| `any-cli-mcp-server` (scrapes `--help`) | **Structured, typed CLI→tool mapping** |
| Enterprise gateways (Kong, Bifrost, MCPX) | **Lightweight, developer-owned, open-source** |
| Visual builders (Langflow, n8n) | **CI/CD-native, GitOps-friendly runtime** |
| `fastmcp.json` (still needs server.py) | **Truly zero-code for CLI tool wrapping** |

**MCPForge** fills this gap: a single binary + gorgeous embedded web UI that reads a declarative YAML spec and spawns a production-ready MCP server at runtime — locally, in CI/CD, or as a hosted remote endpoint.

---

## 1. Vision & Positioning

```
┌──────────────────────────────────────────────────────────────────┐
│                         MCPForge                                 │
│                                                                  │
│  mcp-forge.yaml ──► [Engine] ──► MCP Server (stdio | http | sse)│
│                        │                                         │
│                  [Beautiful UI] ──► visual config + live metrics │
│                        │                                         │
│                    [Registry] ──► publish / discover / reuse     │
└──────────────────────────────────────────────────────────────────┘
```

**Target users — the whole world, not a niche:**
- Any developer who has a CLI tool and wants to make it agent-callable in minutes
- Indie hackers and open-source authors who want to expose their tools to AI workflows
- DevOps engineers running agentic CI/CD pipelines
- Platform teams building internal AI tooling
- Researchers wrapping scripts and datasets as MCP tools
- Literally anyone with a terminal command and an idea

**Positioning:** *"If FastMCP is Flask, MCPForge is Heroku for MCP servers"*

---

## 2. UI Design Philosophy — NON-NEGOTIABLE

> **Beautiful first. Always. No exceptions.**

The embedded UI is not a dashboard bolted on as an afterthought. It IS the product for many users. It needs to be the kind of UI that people screenshot and post on Twitter saying "wait this is actually gorgeous."

### Design Principles

**1. Visually stunning, not "functional-ugly"**
This is not Traefik dashboard. This is not Grafana default theme. This is not "Bootstrap gray."
The UI should feel like a premium developer tool — think Linear, Vercel, Raycast, Oxide Console, Warp terminal. Dark by default, with a light theme option. Every pixel intentional.

**2. Glassmorphism + depth**
Frosted glass panels, subtle gradients, layered z-depth. Tool cards float. Panels breathe. Not garish — refined. The kind of dark theme that makes engineers say "oh" when they first open it.

**3. Micro-interactions everywhere**
- Tool call animations (a pulse ripples from the tool card when it's invoked)
- Arg validation inline (green tick / red shake as you type)
- Live metrics that animate smoothly (not hard number jumps)
- Hover states that reveal context without cluttering the base UI
- "Test Tool" panel slides in from the right like a drawer

**4. Typography with character**
Not Inter. Not Roboto. Something with personality — perhaps `Geist Mono` for code, `Cal Sans` or `Syne` for headings. Clear hierarchy. Monospace for YAML/config that actually looks beautiful.

**5. Real-time feels alive**
Connection status pulses. Live call rates update in real time. The server status indicator in the corner breathes (subtle CSS animation). When a tool is called, you see it happen.

**6. The YAML ↔ UI sync is the magic moment**
When someone edits in the visual builder and watches the YAML update live in the split pane — that's the moment. It should be smooth, instant, satisfying. Same in reverse: paste YAML, watch the form populate.

---

## 3. Use Cases — Universal, Not Niche

MCPForge is for **anything with a CLI, API, or script**. Here are real-world examples across completely different domains:

### Example A: Media & Creative Tools

```yaml
forge:
  name: "creative-studio"
  description: "Wrap ffmpeg, ImageMagick, and yt-dlp as agent tools"

tools:
  - name: convert_video
    description: "Convert any video file to a target format with optional compression"
    adapter: cli
    cli:
      command: "ffmpeg"
      timeout_seconds: 300
    args:
      - name: input_file
        type: string
        required: true
        flag: "-i"
      - name: output_file
        type: string
        required: true
        positional: true
      - name: quality
        type: integer
        default: 23
        flag: "-crf"
        description: "CRF quality (0=lossless, 51=worst). 23 is default."
    output:
      type: exit_code
      success: [0]

  - name: resize_image
    description: "Resize an image to specific dimensions"
    adapter: cli
    cli:
      command: "magick"
    args:
      - name: input
        type: string
        required: true
        positional: 0
      - name: width
        type: integer
        required: true
      - name: height
        type: integer
        required: true
        template: "-resize {width}x{height}"
      - name: output
        type: string
        required: true
        positional: 1
    output:
      type: exit_code

  - name: download_video
    description: "Download a video from YouTube, TikTok, Twitter, or 1000+ other sites"
    adapter: cli
    cli:
      command: "yt-dlp"
      timeout_seconds: 600
    args:
      - name: url
        type: string
        required: true
        positional: true
      - name: format
        type: string
        default: "best"
        flag: "-f"
      - name: output_template
        type: string
        default: "%(title)s.%(ext)s"
        flag: "-o"
    output:
      type: stdout
      streaming: true
```

---

### Example B: System & Infrastructure Tools (Windows, Linux, macOS)

```yaml
forge:
  name: "sysops-toolkit"
  description: "System administration tools as agent-callable MCP tools"

tools:
  - name: disk_usage
    description: "Get disk usage for a path or drive"
    adapter: shell
    shell:
      # Cross-platform via conditional
      command: "du -sh {path} 2>/dev/null || dir {path}"
    args:
      - name: path
        type: string
        default: "."
        description: "Directory path to analyze"
    output:
      type: stdout
      format: text

  - name: list_processes
    description: "List running processes, optionally filtered by name"
    adapter: cli
    cli:
      command: "ps"
      args_template: "aux"
    args:
      - name: filter
        type: string
        required: false
        description: "Optional process name filter"
    output:
      type: stdout
      post_process:
        jq_like: "filter by args.filter if present"

  - name: ping_host
    description: "Check if a host is reachable"
    adapter: cli
    cli:
      command: "ping"
      timeout_seconds: 10
    args:
      - name: host
        type: string
        required: true
        positional: true
      - name: count
        type: integer
        default: 4
        flag: "-c"
    output:
      type: exit_code
      success: [0]
      map:
        1: "Host unreachable"
        2: "Network error"

  - name: run_powershell
    description: "Execute a PowerShell command (Windows)"
    adapter: cli
    cli:
      command: "powershell.exe"
      args_template: "-NonInteractive -Command"
    args:
      - name: script
        type: string
        required: true
        positional: true
    output:
      type: stdout
```

---

### Example C: Data Science & AI Tools

```yaml
forge:
  name: "data-toolkit"
  description: "Python data science scripts exposed as MCP tools"

tools:
  - name: analyze_csv
    description: "Run statistical analysis on a CSV file, return summary as JSON"
    adapter: python
    python:
      module: "tools.analysis"
      function: "analyze"
    args:
      - name: file_path
        type: string
        required: true
      - name: columns
        type: array
        items: string
        required: false
        description: "Specific columns to analyze. Defaults to all."
    output:
      type: json

  - name: run_notebook
    description: "Execute a Jupyter notebook and return output"
    adapter: cli
    cli:
      command: "jupyter"
      subcommand: "nbconvert"
      args_template: "--to notebook --execute {input} --output {output}"
      timeout_seconds: 600
    args:
      - name: input
        type: string
        required: true
        description: "Path to .ipynb file"
      - name: output
        type: string
        default: "output.ipynb"
    output:
      type: file
      path_field: output

  - name: query_duckdb
    description: "Run a SQL query against any local Parquet or CSV file using DuckDB"
    adapter: cli
    cli:
      command: "duckdb"
      args_template: ":memory: -c \"{query}\""
    args:
      - name: query
        type: string
        required: true
        description: "SQL query. Use read_parquet('file.parquet') or read_csv('file.csv')"
    output:
      type: stdout
      format: text
```

---

### Example D: Developer Productivity

```yaml
forge:
  name: "dev-tools"
  description: "Git, npm, Docker and project tools as agent-callable MCP server"

tools:
  - name: git_log
    description: "Get recent git commit history"
    adapter: cli
    cli:
      command: "git"
      subcommand: "log"
      args_template: "--oneline -n {count} --format='{format}'"
    args:
      - name: count
        type: integer
        default: 20
      - name: branch
        type: string
        required: false
        flag: "--branch"
    output:
      type: stdout

  - name: run_tests
    description: "Run the project test suite"
    adapter: shell
    shell:
      command: "npm test 2>&1"
      working_dir: "${PROJECT_ROOT}"
      timeout_seconds: 120
    args: []
    output:
      type: stdout
      streaming: true

  - name: docker_stats
    description: "Get resource usage stats for running Docker containers"
    adapter: cli
    cli:
      command: "docker"
      subcommand: "stats"
      args_template: "--no-stream --format json"
    output:
      type: stdout
      format: json_lines

  - name: build_project
    description: "Build the project and return build output"
    adapter: shell
    shell:
      command: "${BUILD_COMMAND}"
      timeout_seconds: 300
    args:
      - name: target
        type: string
        required: false
        description: "Build target (e.g. 'release', 'debug', 'prod')"
    output:
      type: stdout
      streaming: true
      exit_code_on_failure: true
```

---

### Example E: Home Automation & IoT

```yaml
forge:
  name: "home-automation"
  description: "Control smart home devices via REST APIs"

tools:
  - name: set_light
    description: "Turn a smart light on/off or set brightness and color"
    adapter: rest
    rest:
      base_url: "http://192.168.1.100/api/${HUE_USER}"
      endpoint: "/lights/{light_id}/state"
      method: PUT
    args:
      - name: light_id
        type: integer
        required: true
        path_param: light_id
      - name: on
        type: boolean
        required: false
        body_field: on
      - name: brightness
        type: integer
        required: false
        body_field: bri
        description: "0-254"
      - name: hue
        type: integer
        required: false
        body_field: hue
        description: "0-65535 color wheel"
    output:
      type: json

  - name: get_weather
    description: "Get current weather for a location"
    adapter: rest
    rest:
      base_url: "https://api.open-meteo.com/v1"
      endpoint: "/forecast"
      method: GET
    args:
      - name: latitude
        type: number
        required: true
        query_param: latitude
      - name: longitude
        type: number
        required: true
        query_param: longitude
      - name: current
        type: string
        default: "temperature_2m,wind_speed_10m"
        query_param: current
    output:
      type: json_field
      field: current
```

---

## 4. The Config Format — `mcp-forge.yaml`

Full reference spec — everything in the UI serializes to this.

```yaml
forge:
  name: "my-toolset"               # server identity
  version: "1.0.0"
  description: "Human-readable description for the registry and UI"
  icon: "🔧"                        # emoji or URL for UI display
  tags: [productivity, cli, local]

server:
  transport: http                  # stdio | http | sse | all
  port: 8765
  host: "127.0.0.1"               # 0.0.0.0 for remote access
  path_prefix: "/mcp"
  health_check: true               # GET /health for CI readiness probes
  ui:
    enabled: true                  # serve the web UI
    port: 8766                     # can be same port as MCP, different path
    path: "/ui"
    theme: "dark"                  # dark | light | auto
  cors:
    enabled: true
    origins: ["*"]

auth:
  mode: none                       # none | api_key | oauth2 | jwt | mtls
  # api_key mode:
  api_keys:
    - key: "${FORGE_API_KEY}"
      label: "my-key"
      scopes: [read, execute]

tools:
  - name: tool_name                 # snake_case, used as MCP tool ID
    description: "Clear description — this is what the LLM reads to decide when to use this tool"
    adapter: cli                   # cli | rest | python | shell | openapi | docker | composed
    
    # --- CLI adapter ---
    cli:
      command: "mytool"            # binary name (must be on PATH or absolute)
      subcommand: "subcommand"     # optional subcommand
      args_template: null          # optional positional template
      timeout_seconds: 30
      working_dir: "${PWD}"
      env:
        MY_VAR: "${SOME_ENV_VAR}"

    args:
      - name: arg_name
        type: string               # string | integer | number | boolean | array | object
        required: true
        flag: "--flag"             # CLI flag (-f or --flag)
        positional: false          # or integer for position index
        default: null
        enum: []                   # allowed values
        description: "Description for the LLM"
        secret: false              # redacts from logs and UI

    output:
      type: stdout                 # stdout | stderr | json_field | exit_code | file | structured
      format: text                 # text | json | json_lines | xml | markdown
      streaming: false
      field: null                  # for json_field type
      jq: null                     # for structured type
      on_error: stderr
      exit_codes:
        success: [0]
        map:
          1: "Error: resource not found"
          2: "Error: permission denied"

resources:
  - name: resource_name
    description: "Human-readable description"
    uri: "file://${PWD}/docs/something.md"
    mime_type: "text/markdown"
    volatile: false                # true = changes frequently, clients should re-fetch

prompts:
  - name: prompt_name
    description: "Description of when to use this prompt"
    args:
      - name: context
        required: true
    template: |
      System prompt template with {{context}} interpolation.

env:                               # environment variables for all tools
  PROJECT_ROOT: "${PWD}"
  # Secrets: reference via ${ENV_VAR}, never hardcode

rate_limiting:
  enabled: false
  requests_per_minute: 60
  burst: 10
  per_tool: {}                     # override per tool name

logging:
  level: INFO
  format: json
  output: stdout                   # stdout | file | both
  file: ".forge/forge.log"
  redact_args: true                # never log arg values
  redact_output: true              # never log tool output
  audit: true                      # separate append-only audit log
```

---

## 5. Engine — Processing Pipeline

```
mcp-forge.yaml
     │
     ▼
┌─────────────┐
│   Parser    │  JSON Schema validation, type checking, early error detection
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Resolver   │  Env var expansion, binary existence checks, path validation
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Adapter    │  Selects adapter per tool, generates async handler functions
│  Factory    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  FastMCP    │  Registers tools/resources/prompts, auto-generates JSON Schema
│  Builder    │  from arg definitions (type, required, enum, description)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Gateway    │  Auth enforcement, rate limiting, CORS, input validation
│  Layer      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  MCP Server │  Running — stdio or HTTP
│  + Web UI   │  UI served on separate path by same process
└─────────────┘
```

### 5.1 Adapters

| Adapter | Source | What it wraps |
|---|---|---|
| `cli` | Any CLI binary | Maps typed args → flags, captures outputs |
| `shell` | Shell script | Inline bash/sh/pwsh, env injection |
| `rest` | HTTP endpoint | Auth injection, body/query/path param mapping |
| `python` | Python function | Direct call, no subprocess overhead |
| `openapi` | OpenAPI 3.x spec | **Auto-generates ALL tools from the spec — zero per-tool config** |
| `graphql` | GraphQL schema | Auto-generates query + mutation tools |
| `docker` | Docker image | Spawn container, execute, stream, destroy |
| `grpc` | gRPC service | Proto-based tool generation |
| `composed` | Multiple tools | Pipeline chaining with conditionals |

### 5.2 Output Mapping

The feature `any-cli-mcp-server` gets completely wrong:

```yaml
output:
  type: stdout                    # return raw stdout as string
  type: json_field                # parse JSON stdout, return specific field
    field: "data.results"         # dot notation path
  type: exit_code                 # map exit codes to success/error messages
    success: [0]
    map:
      1: "Not found"
      127: "Command not found — is the tool installed?"
  type: file                      # tool writes a file; return path or contents
    path_field: "output_path"     # field in JSON stdout containing the path
    return: contents              # contents | path
  type: structured                # post-process stdout with jq expression
    jq: ".items[] | select(.status == \"active\")"
  type: streaming                 # progressive output as tool runs
    chunk_size: 1024
```

---

## 6. The Web UI — Beautiful by Design

**Served embedded by MCPForge itself** at `/ui`. No separate deployment, no Docker Compose, no node server. Open the browser, see something stunning.

### Design Language
- **Dark glass** — deep navy/charcoal base, frosted glass panels with subtle border glow
- **Accent color** — electric indigo/violet — used sparingly for live elements and CTAs
- **Typography** — `Geist Mono` for all code/YAML, `Syne` or `Outfit` for UI labels and headings  
- **Motion** — tools pulse when called, metrics animate on update, panels slide in smoothly
- **Density** — information-rich without feeling cluttered. More Linear, less Jira.

### UI Sections

#### 🏠 Dashboard (landing)
- Server status: animated breathing dot (green=live, red=error, amber=starting)
- Active connections panel — which MCP clients are currently connected, with client name and connection time
- Live call heatmap — tool activity as a real-time sparkline per tool
- Key metrics at a glance: total calls today, avg latency, error rate, uptime
- Recent activity feed — last 20 tool calls with tool name, duration, status

#### 🔧 Tools
- Card grid of all configured tools — each card shows: name, adapter type badge, call count, avg latency, last called
- Click a tool → drawer opens from the right:
  - Tool details and description
  - **"Try it"** panel — fill in args with a beautiful form, hit Run, see the live output
  - Live call history for this specific tool
  - Edit button → opens config editor focused on this tool
- Status indicators: healthy / degraded / never called / timeout

#### ⚙️ Config Editor
- Full-width Monaco editor with YAML syntax highlighting + JSON Schema validation
- Split view: YAML left, **Visual form builder right** — fully bidirectional sync
- Changes highlight in real time (diff from saved state)
- Toolbar: Validate → Save → Apply (hot reload without restart) → Download
- Schema errors shown inline with helpful messages ("Expected string, got integer for `timeout_seconds`")
- The visual form builder is drag-and-drop for tool ordering, type-safe arg editing with dropdowns for enums

#### 📊 Metrics
- Full Prometheus-style dashboard, rendered in-UI
- Per-tool charts: call rate, latency p50/p95/p99, error rate
- Time range selector: last 5 min / 1h / 24h / 7d
- Export: Prometheus scrape endpoint at `/metrics`, or download as CSV
- Agent analytics: which tools are actually being used, which are ignored, which error most

#### 🔐 Security
- Auth mode badge (none / api_key / oauth2)
- API key management: create, label, scope, revoke — all in UI
- Per-tool permission matrix: visual grid of (key × tool) with toggle switches
- Audit log viewer: searchable, filterable, never shows arg values (redacted)
- OAuth wizard for remote deployment: step-by-step guide

#### 🌐 Registry
- Search the public MCPForge registry
- Preview tool definitions before importing
- One-click import: merges into current config
- Publish panel: name, tags, visibility, version bump

---

## 7. Security & Auth

### 7.1 Auth Modes

| Mode | Best For |
|---|---|
| `none` | Local dev only — server bound to 127.0.0.1 |
| `api_key` | CI/CD pipelines, internal tooling |
| `jwt` | Existing enterprise SSO (LDAP, Okta, etc.) |
| `oauth2` | Remote hosted MCP servers, per-user auth (MCP spec June 2025) |
| `mtls` | Zero-trust enterprise, highest security |

### 7.2 Tool-Level RBAC

```yaml
auth:
  mode: api_key
  api_keys:
    - key: "${READONLY_KEY}"
      label: "read-only-agent"
      scopes:
        allow_tools: [git_log, disk_usage]
        deny_tools: [run_tests, docker_stats]
    - key: "${ADMIN_KEY}"
      label: "admin-agent"
      scopes: ["*"]               # all tools
```

### 7.3 Built-in Hardening
- **No secrets in logs** — arg values always redacted
- **No path traversal** — file paths validated and sandboxed
- **Subprocess isolation** — CLI tools run with stripped-down env
- **Timeout enforcement** — hard timeout per tool, no runaway processes
- **Input validation** — all args validated against schema before any execution
- **Prompt injection detection** — optional; scans string args for injection patterns
- **Audit trail** — append-only log: who, what tool, when, result code (no args, no output)

---

## 8. CI/CD Integration — First Class

### GitHub Actions
```yaml
- name: Start MCPForge
  run: |
    pip install mcp-forge
    mcp-forge serve --config mcp-forge.yaml --transport http --port 8765 &
    mcp-forge wait-ready --timeout 15    # polls /health

- name: Run agent task
  run: |
    claude --mcp http://localhost:8765/mcp \
      "Analyze git log, run the tests, and if they pass build for release"

- name: Teardown
  if: always()
  run: mcp-forge stop
```

### Docker
```dockerfile
FROM python:3.12-slim
RUN pip install mcp-forge ffmpeg-python yt-dlp
COPY mcp-forge.yaml .
EXPOSE 8765 8766
HEALTHCHECK CMD mcp-forge health
CMD ["mcp-forge", "serve", "--transport", "http"]
```

### `mcp-forge.lock` — Reproducibility
```json
{
  "forge_version": "1.2.0",
  "generated_at": "2026-03-11T09:00:00Z",
  "tools": {
    "convert_video": {
      "cli_binary": "ffmpeg",
      "binary_version": "6.1.1",
      "binary_hash": "sha256:abc123...",
      "adapter_version": "0.3.1"
    }
  }
}
```

---

## 9. What Makes MCPForge AMAZING — Full Brainstorm

### 🤖 AI-Powered Tool Import
The killer feature for onboarding:
- **"Paste --help output"** → AI reads it, generates complete typed `mcp-forge.yaml` tool definition
- **"Paste OpenAPI spec"** → auto-generates ALL tools, zero per-tool config needed
- **"Paste a shell script"** → AI infers args, types, output format
- **"Describe your tool in plain English"** → generates YAML from natural language
- `mcp-forge discover ffmpeg` → runs the binary, interrogates help, generates draft config

### 🔀 Tool Composition — Mini Pipelines
```yaml
tools:
  - name: process_and_report
    adapter: composed
    description: "Download video, convert it, then generate thumbnail"
    steps:
      - tool: download_video
        args: { url: "{{input.url}}" }
        output_as: downloaded
      - tool: convert_video
        args: { input_file: "{{downloaded.path}}", output_file: "{{downloaded.stem}}.mp4" }
        condition: "{{downloaded.success}}"
        output_as: converted
      - tool: extract_thumbnail
        args: { video: "{{converted.path}}", time: "00:00:05" }
    output: "{{thumbnail.path}}"
```
Agent calls one tool, MCPForge orchestrates the pipeline internally. Conditional steps, output piping, the works.

### 🧪 Built-in Test Framework
```bash
mcp-forge test ./tests/
```
```yaml
# tests/convert_video.test.yaml
tool: convert_video
cases:
  - name: "mp4 to webm succeeds"
    args: { input_file: "./fixtures/sample.mp4", output_file: "/tmp/out.webm" }
    expect:
      exit_code: 0
  - name: "missing input fails gracefully"
    args: { input_file: "./fixtures/nonexistent.mp4", output_file: "/tmp/out.webm" }
    expect:
      exit_code: 1
      error_contains: "No such file"
```
Tests run in CI, output JUnit XML, catch regressions before agents hit them.

### 📡 Streaming Output
Long-running tools stream progressive updates:
```yaml
output:
  type: stdout
  streaming: true    # client receives incremental chunks as they arrive
```
The UI shows a live terminal-style output panel while the tool runs.

### 🌍 One-Command Remote Deploy
```bash
mcp-forge deploy --platform cloudflare   # or fly.io, railway, vercel
```
Takes local `mcp-forge.yaml`, generates platform config, deploys as HTTPS remote MCP server with OAuth. The whole world can use your tools.

### 📈 Agent Analytics — Beyond Basic Metrics
Not just call counts. Track:
- Which tools agents use vs. ignore (helps improve descriptions)
- Which arg combinations are most common (helps set better defaults)
- Which tools cause agents to retry or fail (UX signal)
- Cost attribution if tools hit paid APIs
- Exportable to Grafana, Datadog, or any Prometheus-compatible system

### 🛡️ Prompt Injection Shield
Configurable scan of string arguments for patterns that attempt to hijack agent behavior. Especially useful when tools accept user-provided inputs that flow through to the agent.

### 🔄 Hot Reload
Save `mcp-forge.yaml`, tools reload without dropping active connections. Essential for fast iteration.

### 📦 Multi-Forge Composition
```yaml
# combined.yaml
includes:
  - ./video-tools/mcp-forge.yaml
  - ./dev-tools/mcp-forge.yaml
  - registry://community/git-tools@2.1
```
Merge configs, namespace collisions auto-resolved, one server exposes everything.

### 🎯 OpenAPI Auto-Import
```yaml
tools:
  - adapter: openapi
    spec: "https://api.github.com/openapi.json"   # or local file
    include_operations: [listRepos, createIssue, searchCode]
    auth_header: "Authorization: Bearer ${GITHUB_TOKEN}"
```
Hundreds of tools from one line. Every REST API with an OpenAPI spec becomes a full MCP server instantly.

### 💾 Persistent Tool State
Some tools need memory between calls (e.g., a session, a running process). MCPForge provides an optional key-value state store per tool instance.

### 🌐 Multi-Language Adapter Support
While the engine is Python, adapters can call tools in any language. The `docker` adapter is the escape hatch for any exotic runtime (Rust binaries, Node.js scripts, Java tools, etc.).

---

## 10. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Core runtime | Python 3.12 + FastMCP 3.x | FastMCP powers ~70% of MCP ecosystem |
| Web UI | React 19 + Vite + Tailwind + Framer Motion | Beautiful, fast, modern |
| UI components | shadcn/ui + Radix | Accessible, unstyled foundation to customize |
| Code editor | Monaco (same as VSCode) | Best-in-class YAML/JSON editing |
| Config schema | Pydantic v2 + JSON Schema | Validation + IDE autocomplete |
| Metrics | Prometheus client | Universal compatibility |
| Auth | Authlib | OAuth 2.1, PKCE, JWT — the June 2025 MCP spec |
| CLI | Typer | Type-safe, auto-generated help |
| Packaging | `pip install mcp-forge` + `uvx mcp-forge` | Zero friction install |
| Binary dist | PyInstaller / uv | Single binary, no Python required |

---

## 11. Differentiation Matrix

| Feature | **MCPForge** | Kong/Bifrost | any-cli-mcp | FastMCP raw | Langflow |
|---|---|---|---|---|---|
| Zero Python for CLI tools | ✅ | ❌ | ✅ fragile | ❌ | ❌ |
| Typed arg mapping | ✅ | N/A | ❌ | Manual | ❌ |
| Output mapping | ✅ | N/A | ❌ | Manual | Partial |
| **Beautiful embedded UI** | ✅ | ✅ $$$$ | ❌ | ❌ | ✅ (heavy) |
| CI/CD native | ✅ | Partial | ❌ | Partial | ❌ |
| Tool test framework | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tool composition | ✅ | ❌ | ❌ | Manual | ✅ (visual) |
| AI-powered import | ✅ | ❌ | Partial | ❌ | Partial |
| OpenAPI auto-import | ✅ | ✅ | ❌ | ❌ | ✅ |
| Open source | ✅ | ❌ | ✅ | ✅ | ✅ |
| Registry | ✅ | ❌ | ❌ | ❌ | ❌ |
| Lock file | ✅ | ❌ | ❌ | ❌ | ❌ |
| Single binary install | ✅ | ❌ | ✅ | ✅ | ❌ |
| Streaming output | ✅ | Partial | ❌ | Manual | ❌ |
| Price | **Free/OSS** | $$$$ | Free | Free | Free/$$$ |

---

## 12. Roadmap

### v0.1 — MVP (The PoC That Proves It Works)
- [ ] YAML parser + Pydantic schema validation  
- [ ] `cli` and `shell` adapters  
- [ ] Output mapping: stdout, json_field, exit_code  
- [ ] FastMCP server generation at runtime  
- [ ] `stdio` and `http` transports  
- [ ] `api_key` auth  
- [ ] `mcp-forge validate` (CI linting)  
- [ ] `mcp-forge wait-ready` (CI health check loop)
- [ ] Health endpoint `/health`

### v0.2 — It's Actually Beautiful
- [ ] Embedded Web UI (Dashboard + Tools + Config Editor)
- [ ] Bidirectional YAML ↔ visual editor sync
- [ ] "Try it" drawer with live output
- [ ] `rest` adapter
- [ ] Hot reload
- [ ] Basic Prometheus metrics at `/metrics`
- [ ] `mcp-forge discover <binary>` (auto-gen from --help)

### v0.3 — Production Ready
- [ ] OAuth 2.1 + JWT auth
- [ ] Tool-level RBAC
- [ ] Audit log (UI + file)
- [ ] Lock file generation
- [ ] Docker official image
- [ ] Tool test framework + JUnit output
- [ ] AI-powered import (Claude API integration)
- [ ] Streaming output support

### v1.0 — The Platform
- [ ] Public registry + private org registry
- [ ] Tool composition (composed adapter)
- [ ] OpenAPI auto-import adapter
- [ ] One-command remote deploy (Cloudflare / Fly.io)
- [ ] Agent analytics dashboard
- [ ] Prompt injection shield
- [ ] Multi-forge composition
- [ ] Full UI metrics dashboard with charts

---

## 13. Name & Branding

| Name | Vibe |
|---|---|
| **MCPForge** | Industrial craft — you forge tools. Strong. |
| **Forge** | Short, punchy. `forge serve`. Might be taken. |
| **mcpify** | Verb-based — "mcpify your tools" |
| **toolcast** | Casting tools into MCP shape |
| **mcpd** | Unix daemon naming — ops-friendly |
| **Welder** | You weld your CLI tools into MCP servers |

**MCPForge** still wins. Domain: `mcpforge.dev` — check availability.

---

*Draft v0.2 — March 2026*  
*UI-first. World-scale. No niche BS.*
