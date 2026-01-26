# Prometheus MCP Server

[![GitHub Container Registry](https://img.shields.io/badge/ghcr.io-pab1it0%2Fprometheus--mcp--server-blue?logo=docker)](https://github.com/users/pab1it0/packages/container/package/prometheus-mcp-server)
[![GitHub Release](https://img.shields.io/github/v/release/pab1it0/prometheus-mcp-server)](https://github.com/pab1it0/prometheus-mcp-server/releases)
[![Codecov](https://codecov.io/gh/pab1it0/prometheus-mcp-server/branch/main/graph/badge.svg)](https://codecov.io/gh/pab1it0/prometheus-mcp-server)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License](https://img.shields.io/github/license/pab1it0/prometheus-mcp-server)](https://github.com/pab1it0/prometheus-mcp-server/blob/main/LICENSE)

Give AI assistants the power to query your Prometheus metrics.

A [Model Context Protocol][mcp] (MCP) server that provides access to your Prometheus metrics and queries through standardized MCP interfaces, allowing AI assistants to execute PromQL queries and analyze your metrics data.

[mcp]: https://modelcontextprotocol.io

## Getting Started

### Prerequisites

- Prometheus server accessible from your environment
- MCP-compatible client (Claude Desktop, VS Code, Cursor, Windsurf, etc.)

### Installation Methods

<details>
<summary><b>Claude Desktop</b></summary>

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "PROMETHEUS_URL",
        "ghcr.io/pab1it0/prometheus-mcp-server:latest"
      ],
      "env": {
        "PROMETHEUS_URL": "<your-prometheus-url>"
      }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b></summary>

Install via the Claude Code CLI:

```bash
claude mcp add prometheus --env PROMETHEUS_URL=http://your-prometheus:9090 -- docker run -i --rm -e PROMETHEUS_URL ghcr.io/pab1it0/prometheus-mcp-server:latest
```
</details>

<details>
<summary><b>VS Code / Cursor / Windsurf</b></summary>

Add to your MCP settings in the respective IDE:

```json
{
  "prometheus": {
    "command": "docker",
    "args": [
      "run",
      "-i",
      "--rm",
      "-e",
      "PROMETHEUS_URL",
      "ghcr.io/pab1it0/prometheus-mcp-server:latest"
    ],
    "env": {
      "PROMETHEUS_URL": "<your-prometheus-url>"
    }
  }
}
```
</details>

<details>
<summary><b>Docker Desktop</b></summary>

The easiest way to run the Prometheus MCP server is through Docker Desktop:

<a href="https://hub.docker.com/open-desktop?url=https://open.docker.com/dashboard/mcp/servers/id/prometheus/config?enable=true">
  <img src="https://img.shields.io/badge/+%20Add%20to-Docker%20Desktop-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Add to Docker Desktop" />
</a>

1. **Via MCP Catalog**: Visit the [Prometheus MCP Server on Docker Hub](https://hub.docker.com/mcp/server/prometheus/overview) and click the button above

2. **Via MCP Toolkit**: Use Docker Desktop's MCP Toolkit extension to discover and install the server

3. Configure your connection using environment variables (see Configuration Options below)

</details>

<details>
<summary><b>Manual Docker Setup</b></summary>

Run directly with Docker:

```bash
# With environment variables
docker run -i --rm \
  -e PROMETHEUS_URL="http://your-prometheus:9090" \
  ghcr.io/pab1it0/prometheus-mcp-server:latest

# With authentication
docker run -i --rm \
  -e PROMETHEUS_URL="http://your-prometheus:9090" \
  -e PROMETHEUS_USERNAME="admin" \
  -e PROMETHEUS_PASSWORD="password" \
  ghcr.io/pab1it0/prometheus-mcp-server:latest
```
</details>

### Configuration Options

| Variable | Description | Required |
|----------|-------------|----------|
| `PROMETHEUS_URL` | URL of your Prometheus server (required unless `PROMETHEUS_TENANTS` is set) | Yes* |
| `PROMETHEUS_URL_SSL_VERIFY` | Set to False to disable SSL verification | No |
| `PROMETHEUS_DISABLE_LINKS` | Set to True to disable Prometheus UI links in query results (saves context tokens) | No |
| `PROMETHEUS_REQUEST_TIMEOUT` | Request timeout in seconds to prevent hanging requests (DDoS protection) | No (default: 30) |
| `PROMETHEUS_USERNAME` | Username for basic authentication | No |
| `PROMETHEUS_PASSWORD` | Password for basic authentication | No |
| `PROMETHEUS_TOKEN` | Bearer token for authentication | No |
| `ORG_ID` | Organization ID for multi-tenant setups | No |
| `PROMETHEUS_TENANTS` | JSON array of tenant configs (name, url, optional auth) | No |
| `PROMETHEUS_DEFAULT_TENANT` | Default tenant name when `PROMETHEUS_TENANTS` is set | No |
| `PROMETHEUS_MCP_SERVER_TRANSPORT` | Transport mode (stdio, http, sse) | No (default: stdio) |
| `PROMETHEUS_MCP_BIND_HOST` | Host for HTTP transport | No (default: 127.0.0.1) |
| `PROMETHEUS_MCP_BIND_PORT` | Port for HTTP transport | No (default: 8080) |
| `PROMETHEUS_CUSTOM_HEADERS` | Custom headers as JSON string | No |
| `TOOL_PREFIX` | Prefix for all tool names (e.g., `staging` results in `staging_execute_query`). Useful for running multiple instances targeting different environments in Cursor | No |

### MCP Client Configuration

#### Single tenant

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "PROMETHEUS_URL",
        "ghcr.io/pab1it0/prometheus-mcp-server:latest"
      ],
      "env": {
        "PROMETHEUS_URL": "<url>"
      }
    }
  }
}
```

#### Multi-tenant

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "PROMETHEUS_TENANTS",
        "-e",
        "PROMETHEUS_DEFAULT_TENANT",
        "ghcr.io/pab1it0/prometheus-mcp-server:latest"
      ],
      "env": {
        "PROMETHEUS_TENANTS": "[{\"name\":\"prod\",\"url\":\"https://prometheus.example.com\",\"token\":\"your_token\"}]",
        "PROMETHEUS_DEFAULT_TENANT": "prod"
      }
    }
  }
}
```

### Multi-tenant configuration

Use `PROMETHEUS_TENANTS` to define multiple Prometheus/Thanos endpoints. Each tenant can provide its own URL and auth fields. If `PROMETHEUS_DEFAULT_TENANT` is not set, the first tenant becomes the default.

```bash
PROMETHEUS_TENANTS='[
  {
    "name": "production",
    "url": "https://prometheus-prod.example.com",
    "username": "prod_user",
    "password": "prod_password",
    "org_id": "org-prod"
  },
  {
    "name": "staging",
    "url": "https://prometheus-staging.example.com",
    "token": "staging_bearer_token"
  },
  {
    "name": "development",
    "url": "http://localhost:9090"
  }
]'
PROMETHEUS_DEFAULT_TENANT=production
```

When multi-tenant is enabled, all query tools accept an optional `tenant` parameter (defaults to `PROMETHEUS_DEFAULT_TENANT`).

`list_tenants` returns a minimal tenant summary by default. To include URLs, call it with `include_urls: true`.

### How to use (multi-tenant)

1) Configure tenants

```bash
PROMETHEUS_TENANTS='[
  {"name":"blue","url":"https://blue-prometheus.example.com"},
  {"name":"black","url":"https://black-prometheus.example.com"},
  {"name":"mgmt","url":"https://mgmt-thanos.example.com"}
]'
PROMETHEUS_DEFAULT_TENANT=mgmt
```

2) Call tools with tenant selection (example JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": "q1",
  "method": "tools/call",
  "params": {
    "name": "execute_query",
    "arguments": {
      "query": "count(up)",
      "tenant": "blue"
    }
  }
}
```

### Verification (simple)

Use `count(up)` to verify each tenant responds with data:

- tenant `mgmt`: `count(up)` returns a vector result
- tenant `blue`: `count(up)` returns a vector result
- tenant `black`: `count(up)` returns a vector result

If a tenant is unreachable or misconfigured, the tool call returns an MCP error.

### Transport and streaming

This server supports MCP `stdio`, `http`, and `sse` transports. Use `sse` when you want streaming responses over HTTP. The `http` transport is request/response (non-streaming).

```bash
# Run as an HTTP server with streaming (SSE)
PROMETHEUS_MCP_SERVER_TRANSPORT=sse
PROMETHEUS_MCP_BIND_HOST=0.0.0.0
PROMETHEUS_MCP_BIND_PORT=8080
```

### Communication optimizations

- Prefer `sse` for streaming in remote MCP clients.
- Use `PROMETHEUS_DISABLE_LINKS=True` to reduce response payloads if you don't need UI links.
- Connection reuse is enabled for Prometheus API calls to reduce handshake overhead.

### In-cluster Service Access (Kubernetes)

When running in Kubernetes, point `PROMETHEUS_URL` (or tenant URLs) to the Service DNS:

```text
http://<service>.<namespace>.svc.cluster.local:<port>
```

Example:

```text
http://prometheus.monitoring.svc.cluster.local:9090
```

## Available Tools

| Tool | Category | Description |
| --- | --- | --- |
| `health_check` | System | Health check endpoint for container monitoring and status verification |
| `execute_query` | Query | Execute a PromQL instant query against Prometheus |
| `execute_range_query` | Query | Execute a PromQL range query with start time, end time, and step interval |
| `list_metrics` | Discovery | List all available metrics in Prometheus with pagination and filtering support |
| `get_metric_metadata` | Discovery | Get metadata for a specific metric |
| `get_targets` | Discovery | Get information about all scrape targets |
| `list_tenants` | Discovery | List configured Prometheus tenants (when multi-tenant is enabled) |

The list of tools is configurable, so you can choose which tools you want to make available to the MCP client. This is useful if you don't use certain functionality or if you don't want to take up too much of the context window.

## Features

- Execute PromQL queries against Prometheus
- Discover and explore metrics
  - List available metrics
  - Get metadata for specific metrics
  - View instant query results
  - View range query results with different step intervals
- Authentication support
  - Basic auth from environment variables
  - Bearer token auth from environment variables
- Docker containerization support
- Provide interactive tools for AI assistants

## Development

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for detailed information on how to get started, coding standards, and the pull request process.

This project uses [`uv`](https://github.com/astral-sh/uv) to manage dependencies. Install `uv` following the instructions for your platform:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

You can then create a virtual environment and install the dependencies with:

```bash
uv venv
source .venv/bin/activate  # On Unix/macOS
.venv\Scripts\activate     # On Windows
uv pip install -e .
```

### Testing

The project includes a comprehensive test suite that ensures functionality and helps prevent regressions.

Run the tests with pytest:

```bash
# Install development dependencies
uv pip install -e ".[dev]"

# Run the tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing
```

When adding new features, please also add corresponding tests.

## License

MIT

---
