# MCPForge — Architecture & Feature Spec v0.1
**"Spawn production-grade MCP servers from config"**

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

**MCPForge** fills this gap: a single binary + embedded web UI that reads a declarative YAML spec and spawns a production-ready MCP server at runtime — locally, in CI/CD, or as a hosted remote endpoint.

---

## 1. Vision & Positioning

```
┌──────────────────────────────────────────────────────────────────┐
│                         MCPForge                                 │
│                                                                  │
│  mcp-forge.yaml ──► [Engine] ──► MCP Server (stdio | http | sse)│
│                        │                                         │
│                    [Web UI]  ──► visual config + live metrics    │
│                        │                                         │
│                    [Registry] ──► publish / discover / reuse     │
└──────────────────────────────────────────────────────────────────┘
```

**Target users:**
- Embedded/automotive/enterprise engineers who have CLI tools and want agent integration **now**
- DevOps engineers who want MCP servers in CI/CD pipelines
- Platform teams who want to govern, monitor and expose internal tools as MCP endpoints
- Researchers who want to wrap scripts as AI-callable tools without writing servers

**Positioning:** *"If FastMCP is Flask, MCPForge is Heroku for MCP servers"*

---

## 2. Core Architecture

### 2.1 Component Map

```
mcpforge/
├── engine/           # Core: config parser + FastMCP server generator
├── ui/               # Embedded lightweight web UI (served by the engine)
├── gateway/          # Auth, rate-limiting, routing layer
├── registry/         # Tool catalog, versioning, sharing
├── adapters/         # CLI, REST API, Python fn, OpenAPI adapters
├── observability/    # Metrics, logs, traces
└── cli/              # `mcp-forge` command line interface
```

### 2.2 Runtime Modes

| Mode | Use Case | Transport |
|---|---|---|
| `mcp-forge serve` | Local dev / Claude Desktop | stdio |
| `mcp-forge serve --http` | CI/CD, agentic pipelines | HTTP / SSE |
| `mcp-forge serve --remote` | Hosted public endpoint | HTTPS + OAuth |
| `mcp-forge run --once` | Single-shot execution | stdio |
| `mcp-forge validate` | CI linting, no server spawn | — |

---

## 3. The Config Format — `mcp-forge.yaml`

This is the heart of MCPForge. Everything expressible in the UI is serializable to this file.

```yaml
# mcp-forge.yaml — the complete declarative spec

forge:
  name: "compliance-checker"
  version: "1.2.0"
  description: "MISRA-C and AUTOSAR compliance tools for embedded CI pipelines"
  tags: [automotive, compliance, embedded, bosch]

server:
  transport: http          # stdio | http | sse | all
  port: 8765
  host: "0.0.0.0"
  path_prefix: "/mcp"
  health_check: true       # GET /health endpoint for CI readiness probes
  cors:
    enabled: true
    origins: ["http://localhost:*"]

auth:
  mode: api_key            # none | api_key | oauth2 | jwt | mtls
  api_keys:
    - key: "${FORGE_API_KEY}"
      label: "ci-pipeline-key"
      scopes: [read, execute]
  # oauth2:
  #   provider: "https://auth.bosch.com"
  #   client_id: "${OAUTH_CLIENT_ID}"

tools:
  - name: check_file
    description: "Run MISRA-C compliance check on a single C source file"
    adapter: cli
    cli:
      command: "compliance-tool"
      subcommand: "check"
      timeout_seconds: 30
      working_dir: "${PROJECT_ROOT}"
    args:
      - name: file_path
        type: string
        required: true
        flag: "--file"
        description: "Absolute path to the .c file to check"
      - name: ruleset
        type: string
        default: "MISRA-C:2012"
        enum: ["MISRA-C:2004", "MISRA-C:2012", "AUTOSAR-C++14"]
        flag: "--ruleset"
      - name: fail_on_warning
        type: boolean
        default: false
        flag: "--strict"
    output:
      type: stdout           # stdout | stderr | json_field | exit_code | file
      format: text           # text | json | xml | markdown
      on_error: stderr       # where to find error details

  - name: batch_check
    description: "Check all C files in a directory recursively"
    adapter: cli
    cli:
      command: "compliance-tool"
      subcommand: "batch"
      timeout_seconds: 120
    args:
      - name: directory
        type: string
        required: true
        flag: "--dir"
      - name: output_format
        type: string
        default: "json"
        enum: ["json", "html", "sarif"]   # SARIF = GitHub code scanning format!
        flag: "--format"
    output:
      type: json_field
      field: "results"
      on_error: json_field:error

  - name: generate_report
    description: "Generate HTML compliance report from last scan results"
    adapter: cli
    cli:
      command: "compliance-tool"
      subcommand: "report"
    args:
      - name: output_dir
        type: string
        required: true
        flag: "--out"
    output:
      type: file
      path_field: "report_path"   # tool returns JSON with this field pointing to the file

  # REST API adapter example
  - name: lookup_rule
    description: "Look up MISRA rule details from the internal knowledge base"
    adapter: rest
    rest:
      base_url: "https://internal-kb.bosch.net/api"
      endpoint: "/misra/rules/{rule_id}"
      method: GET
      auth_header: "Authorization: Bearer ${KB_TOKEN}"
    args:
      - name: rule_id
        type: string
        required: true
        path_param: rule_id

  # Python function adapter example
  - name: parse_sarif
    description: "Parse a SARIF file and return structured violation summary"
    adapter: python
    python:
      module: "forge_tools.sarif_parser"
      function: "parse_and_summarize"
    args:
      - name: sarif_path
        type: string
        required: true

resources:
  - name: ruleset_docs
    description: "MISRA-C 2012 rule reference documentation"
    uri: "file://${PROJECT_ROOT}/docs/misra-c-2012.md"
    mime_type: "text/markdown"

  - name: last_scan_results
    description: "Results from the most recent compliance scan"
    uri: "file://${PROJECT_ROOT}/.forge/last-scan.json"
    mime_type: "application/json"
    volatile: true    # tells clients this changes frequently

prompts:
  - name: review_violations
    description: "Standard prompt template for reviewing compliance violations"
    template: |
      You are a senior embedded systems engineer reviewing MISRA-C compliance results.
      Analyze the following violations and provide:
      1. Severity assessment for each
      2. Recommended fix approach
      3. Whether any can be justified/suppressed
      
      Results: {{results}}

env:
  PROJECT_ROOT: "${PWD}"
  COMPLIANCE_LICENSE: "${COMPLIANCE_LICENSE_KEY}"
  # Secrets are never logged or exposed via UI

rate_limiting:
  enabled: true
  requests_per_minute: 60
  burst: 10

logging:
  level: INFO              # DEBUG | INFO | WARN | ERROR
  format: json             # text | json
  output: stdout           # stdout | file | both
  file: ".forge/forge.log"
  include_tool_args: false  # IMPORTANT: false for security (no secrets in logs)
  include_tool_output: false
```

---

## 4. Engine — Core Processing Pipeline

```
mcp-forge.yaml
     │
     ▼
┌─────────────┐
│   Parser    │  Validates YAML schema (JSON Schema), catches errors early
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Resolver   │  Expands env vars, resolves paths, checks binary existence
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Adapter    │  Selects adapter (CLI / REST / Python / OpenAPI)
│  Factory    │  and generates the tool handler functions
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  FastMCP    │  Registers tools, resources, prompts with FastMCP
│  Builder    │  Generates schema from arg definitions automatically
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Gateway    │  Applies auth, rate-limiting, CORS
│  Layer      │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ MCP Server  │  Running and ready — stdio or HTTP
│  (running)  │
└─────────────┘
```

### 4.1 Adapters (Extensible)

| Adapter | Source | Description |
|---|---|---|
| `cli` | Any CLI tool | Maps args to flags, captures stdout/stderr/exit |
| `rest` | REST endpoints | HTTP wrapper with auth injection |
| `python` | Python functions | Direct function call (no subprocess) |
| `openapi` | OpenAPI 3.x spec | **Auto-generates all tools from spec** |
| `graphql` | GraphQL schema | Auto-generates query tools |
| `shell` | Shell scripts | Inline bash/sh execution |
| `docker` | Docker container | Spawn container, call tool, destroy |
| `grpc` | gRPC services | Proto-based tool generation |

The `openapi` adapter is particularly powerful: point it at a `swagger.json` and every endpoint becomes an MCP tool automatically. Zero config per-tool.

### 4.2 Output Mapping

This is what `any-cli-mcp-server` gets wrong. MCPForge handles:

```yaml
output:
  type: stdout            # raw stdout as text response
  type: json_field        # parse JSON, return specific field
    field: "results"
  type: exit_code         # map exit codes to success/error
    success: [0]
    failure: [1, 2]
    map:
      1: "Compliance violations found"
      2: "Tool license error"
  type: file              # tool writes a file, return path or contents
    path_field: "output"
    return: contents      # or "path"
  type: structured        # post-process with jq expression
    jq: ".violations[] | select(.severity == \"error\")"
```

---

## 5. Embedded Web UI

**Philosophy:** Light, embedded, no separate deployment. Served by the engine itself at `http://localhost:8765/ui`. Think Flower (Celery) or Traefik dashboard — functional, not pretty.

### 5.1 UI Sections

#### 🔧 Tool Builder (Visual Config)
- Drag-and-drop tool definition
- Adapter selector (CLI / REST / Python / OpenAPI)
- Argument editor with type validation
- Live YAML preview (bidirectional sync — edit YAML, UI updates and vice versa)
- **"Test Tool" button** → runs the tool with test args, shows raw output
- **"Import from --help"** → pastes CLI help text, AI parses it into tool definitions (MCPForge calls a lightweight LLM for this)

#### 📊 Live Dashboard
- Active connections (which MCP clients are connected)
- Tool call rate (calls/min per tool)
- Latency histogram per tool
- Error rate with last error message
- Total calls since start
- Export metrics → Prometheus format

#### 🔐 Security Panel
- Active API keys (create / revoke / scope)
- OAuth config wizard
- Per-tool permission matrix (which key can call which tool)
- Audit log viewer (last N calls with args redacted)

#### 📁 Config Editor
- Monaco-based YAML editor with JSON Schema validation
- Real-time error highlighting
- "Apply & Reload" without restart (hot reload)
- Config diff view (current vs saved)
- Export as `mcp-forge.yaml` or `mcp-forge.lock`

#### 🌐 Registry Browser
- Browse public/private tool registry
- One-click import tool definitions into current config
- Publish your tools to registry

---

## 6. Security & Auth

Enterprise MCP security is an active, messy space. MCPForge needs to be opinionated here.

### 6.1 Auth Modes

```
none        → local dev only, bind to 127.0.0.1
api_key     → static keys with scopes, good for CI/CD
jwt         → verify tokens from existing IdP (Bosch SSO, etc.)
oauth2      → full OAuth 2.1 flow with PKCE (June 2025 MCP spec)
mtls        → mutual TLS for zero-trust enterprise environments
```

### 6.2 Tool-Level RBAC

```yaml
auth:
  mode: api_key
  api_keys:
    - key: "${CI_KEY}"
      label: "github-actions"
      scopes:
        allow_tools: [check_file, batch_check]  # not generate_report
        allow_resources: [ruleset_docs]
```

### 6.3 Security Hardening (built-in, non-optional)
- **No secrets in logs** — tool args are redacted by default
- **No path traversal** — file paths are validated and sandboxed
- **Subprocess isolation** — CLI tools run with restricted env
- **Timeout enforcement** — every tool has a hard timeout
- **Input validation** — all args validated against schema before execution
- **Prompt injection detection** — optional scan of string args for injection patterns
- **Audit trail** — append-only log of every tool call (who, what, when, result)

---

## 7. CI/CD Integration

This is a first-class citizen, not an afterthought.

### 7.1 GitHub Actions Example
```yaml
- name: Start MCPForge
  run: |
    pip install mcp-forge
    mcp-forge serve --config mcp-forge.yaml --transport http --port 8765 &
    mcp-forge wait-ready --timeout 10  # health check loop

- name: Run compliance agent
  run: |
    # Any MCP-compatible agent runner
    claude-code --mcp http://localhost:8765/mcp \
      "Run batch_check on ./src, fail if any AUTOSAR violations found"

- name: Stop MCPForge
  if: always()
  run: mcp-forge stop
```

### 7.2 Docker-native
```dockerfile
FROM python:3.11-slim
RUN pip install mcp-forge compliance-tool
COPY mcp-forge.yaml .
EXPOSE 8765
HEALTHCHECK CMD mcp-forge health --port 8765
CMD ["mcp-forge", "serve", "--transport", "http"]
```

### 7.3 `mcp-forge.lock`
Like `poetry.lock` — pins exact tool versions, binary hashes, adapter versions. Enables reproducible CI builds.

```json
{
  "forge_version": "1.2.0",
  "generated_at": "2026-03-11T08:00:00Z",
  "tools": {
    "check_file": {
      "cli_binary": "compliance-tool",
      "binary_hash": "sha256:abc123...",
      "adapter_version": "0.3.1"
    }
  }
}
```

---

## 8. Registry — Tool Catalog

What makes this **amazing** vs. just useful.

### 8.1 Concept
A registry of reusable tool definitions — like Docker Hub but for MCP tool configs.

```bash
mcp-forge registry search "misra compliance"
mcp-forge registry pull bosch/compliance-checker@1.2.0
mcp-forge registry push ./mcp-forge.yaml --name myorg/my-tool
```

### 8.2 Registry Entry Format
```yaml
# registry.yaml (published metadata)
name: bosch/compliance-checker
version: 1.2.0
description: "MISRA-C and AUTOSAR compliance tools"
requires:
  binaries: [compliance-tool>=2.0]
  python: ">=3.10"
tools: [check_file, batch_check, generate_report]
tags: [automotive, embedded, compliance, misra]
license: MIT
verified: true    # MCPForge team verified it works
```

### 8.3 Registry Tiers
- **Public** — open-source tools, community-verified
- **Private** — org-scoped (self-hosted registry server)
- **Certified** — MCPForge team-tested, security-audited

---

## 9. What Would Make This AMAZING — Brainstorm

Beyond the core, these features separate MCPForge from everything else:

### 🤖 AI-Powered Tool Import
- Paste any `--help` output → AI generates complete tool definition
- Paste any OpenAPI spec → auto-generates all tools
- Paste a shell script → AI infers args, types, outputs
- **"Describe your tool in plain English"** → generates the YAML

### 🔀 Tool Composition
```yaml
tools:
  - name: compliance_report_pipeline
    adapter: composed
    steps:
      - tool: batch_check
        args: { directory: "{{input.src_dir}}" }
        output_as: scan_results
      - tool: generate_report
        args: { output_dir: "{{input.out_dir}}" }
        condition: "{{scan_results.violation_count}} > 0"
```
Chain tools into mini-pipelines, with conditionals. Agent calls one tool, MCPForge orchestrates the rest.

### 🧪 Built-in Testing Framework
```bash
mcp-forge test ./tests/
```
```yaml
# tests/check_file.test.yaml
tool: check_file
cases:
  - name: "valid file passes"
    args: { file_path: "./fixtures/clean.c", ruleset: "MISRA-C:2012" }
    expect:
      exit_code: 0
      output_contains: "0 violations"
  - name: "violating file fails"
    args: { file_path: "./fixtures/violations.c" }
    expect:
      exit_code: 1
      output_contains: "violation"
```
Test your MCP tools before deploying them. CI-friendly, reports in JUnit XML.

### 📡 Live Tool Streaming
For long-running tools, stream output progressively to the MCP client instead of buffering:
```yaml
output:
  type: stdout
  streaming: true    # sends incremental updates during execution
```

### 🌍 Remote Hosting Mode
```bash
mcp-forge deploy --cloud cloudflare  # or vercel, fly.io, railway
```
One command to take a local `mcp-forge.yaml` and host it as a remote MCP server with HTTPS + OAuth. MCPForge handles the infra template.

### 🔍 Schema Auto-Discovery
```bash
mcp-forge discover compliance-tool
```
MCPForge runs the CLI binary with various `--help` flags, interrogates it, and generates a draft `mcp-forge.yaml` as a starting point. Better than `any-cli-mcp-server` because you get a structured editable file.

### 📈 Agent Analytics
Beyond basic metrics — track **which tools agents actually use**, which they ignore, which fail most. Feed this back to help engineers improve tool descriptions and defaults.

### 🛡️ Prompt Injection Shield
Scan incoming string arguments for patterns that could hijack the agent. Especially critical for tools that accept user-provided file paths or query strings.

### 🔄 Hot Reload
Edit `mcp-forge.yaml`, save, server reloads tools without dropping connections. Critical for dev iteration.

### 📦 Multi-Server Composition
```yaml
# mcp-forge-multi.yaml
includes:
  - ./compliance/mcp-forge.yaml
  - ./reporting/mcp-forge.yaml
  - registry://bosch/shared-tools@2.0
```
Merge multiple forge configs into one server. Tool namespacing prevents conflicts.

---

## 10. Tech Stack Recommendation

| Layer | Choice | Rationale |
|---|---|---|
| Core runtime | Python + FastMCP | FastMCP powers 70% of MCP servers, excellent ecosystem |
| Web UI | React + Vite | Bundled into the Python package as static assets |
| Config schema | JSON Schema + Pydantic | Validation + IDE autocomplete for free |
| Metrics | Prometheus client | Standard, works with every monitoring stack |
| Auth | Authlib | OAuth 2.1, JWT, handles the June 2025 MCP spec |
| CLI | Typer | Clean, type-safe CLI |
| Packaging | single `pip install mcp-forge` | One dependency, batteries included |
| Binary distribution | PyInstaller / uv | Single binary for non-Python users |

---

## 11. Differentiation vs. Existing Solutions

| Feature | MCPForge | Kong/Bifrost | any-cli-mcp-server | FastMCP raw |
|---|---|---|---|---|
| Zero Python for CLI tools | ✅ | ❌ | ✅ (fragile) | ❌ |
| Typed arg mapping | ✅ | N/A | ❌ | Manual |
| Output mapping (stdout/JSON/file) | ✅ | N/A | ❌ | Manual |
| Embedded Web UI | ✅ | ✅ (enterprise) | ❌ | ❌ |
| CI/CD native | ✅ | Partial | ❌ | Partial |
| Tool testing framework | ✅ | ❌ | ❌ | ❌ |
| Tool composition | ✅ | ❌ | ❌ | Manual |
| AI-powered import | ✅ | ❌ | Partial | ❌ |
| Open source | ✅ | ❌ (enterprise) | ✅ | ✅ |
| Registry | ✅ | ❌ | ❌ | ❌ |
| Lock file | ✅ | ❌ | ❌ | ❌ |
| Price | Free / OSS | $$$$ | Free | Free |

---

## 12. Roadmap

### v0.1 — MVP (the PoC)
- [ ] YAML parser + schema validation
- [ ] CLI adapter (stdout, json, exit_code outputs)
- [ ] FastMCP server generation
- [ ] `stdio` and `http` transports
- [ ] `api_key` auth
- [ ] `mcp-forge validate` command
- [ ] Health check endpoint
- [ ] Basic metrics (Prometheus)

### v0.2 — Developer Experience
- [ ] Embedded Web UI (config editor + tool tester)
- [ ] REST adapter
- [ ] Hot reload
- [ ] `mcp-forge discover <binary>` (auto-gen from --help)
- [ ] AI-powered import (calls Claude API)

### v0.3 — Enterprise Ready
- [ ] OAuth 2.1
- [ ] Tool-level RBAC
- [ ] Audit log
- [ ] Lock file
- [ ] Docker image
- [ ] Tool testing framework

### v1.0 — Platform
- [ ] Registry (public)
- [ ] Tool composition
- [ ] One-command cloud deploy
- [ ] OpenAPI adapter
- [ ] Streaming output
- [ ] Prompt injection shield

---

## 13. Name & Branding Options

| Name | Vibe |
|---|---|
| **MCPForge** | Industrial, builds things, "forge a server" |
| **forge-mcp** | CLI-tool-first naming convention |
| **mcpctl** | kubectl-vibes, ops-friendly |
| **toolbox-mcp** | Accessible, developer-friendly |
| **mcpify** | Verb-based, "mcpify your CLI" |
| **servemcp** | Literal, memorable |

**MCPForge** wins. It implies creation, durability, and craft — which is the whole point.

---

*Draft v0.1 — Mihai Ciprian / March 2026*
*Status: Pre-PoC brainstorm — validate with a working CLI adapter first*
