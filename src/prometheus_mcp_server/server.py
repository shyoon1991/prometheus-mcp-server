#!/usr/bin/env python

import os
import json
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import time
from datetime import datetime, timedelta
from enum import Enum

import dotenv
import requests
from requests.adapters import HTTPAdapter
from fastmcp import FastMCP, Context
from prometheus_mcp_server.logging_config import get_logger

dotenv.load_dotenv()

# Get tool prefix from environment (empty string for backward compatibility)
TOOL_PREFIX = os.environ.get("TOOL_PREFIX", "")

def _tool_name(name: str) -> str:
    """Build tool name with optional prefix."""
    return f"{TOOL_PREFIX}_{name}" if TOOL_PREFIX else name

# Include prefix in MCP server name if set
mcp_name = f"Prometheus MCP ({TOOL_PREFIX})" if TOOL_PREFIX else "Prometheus MCP"
mcp = FastMCP(mcp_name)

# Cache for metrics list to improve completion performance (per-tenant)
_metrics_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 300  # 5 minutes

# Get logger instance
logger = get_logger()

# Reuse HTTP connections for Prometheus API requests
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
_session.mount("http://", _adapter)
_session.mount("https://", _adapter)

# Health check tool for Docker containers and monitoring
@mcp.tool(
    name=_tool_name("health_check"),
    description="Health check endpoint for container monitoring and status verification",
    annotations={
        "title": "Health Check",
        "icon": "❤️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def health_check() -> Dict[str, Any]:
    """Return health status of the MCP server and Prometheus connection.

    Returns:
        Health status including service information, configuration, and connectivity
    """
    try:
        initialize_tenants()
        health_status = {
            "status": "healthy",
            "service": "prometheus-mcp-server",
            "version": "1.5.3",
            "timestamp": datetime.utcnow().isoformat(),
            "transport": config.mcp_server_config.mcp_server_transport if config.mcp_server_config else "stdio",
            "configuration": {
                "prometheus_url_configured": bool(config.url),
                "authentication_configured": bool(config.username or config.token),
                "org_id_configured": bool(config.org_id),
                "tenants_configured": bool(config.tenants),
                "tenant_count": len(config.tenants) if config.tenants else 0,
                "default_tenant": config.default_tenant
            }
        }
        
        # Test Prometheus connectivity if configured
        if config.tenants or config.url:
            try:
                # Quick connectivity test
                make_prometheus_request("query", params={"query": "up", "time": str(int(time.time()))}, tenant=config.default_tenant)
                health_status["prometheus_connectivity"] = "healthy"
                health_status["prometheus_url"] = _get_base_url(config.default_tenant)
            except Exception as e:
                health_status["prometheus_connectivity"] = "unhealthy"
                health_status["prometheus_error"] = str(e)
                health_status["status"] = "degraded"
        else:
            health_status["status"] = "unhealthy"
            health_status["error"] = "PROMETHEUS_URL not configured"
        
        logger.info("Health check completed", status=health_status["status"])
        return health_status
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "service": "prometheus-mcp-server",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


class TransportType(str, Enum):
    """Supported MCP server transport types."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"

    @classmethod
    def values(cls) -> list[str]:
        """Get all valid transport values."""
        return [transport.value for transport in cls]

@dataclass
class MCPServerConfig:
    """Global Configuration for MCP."""
    mcp_server_transport: TransportType = None
    mcp_bind_host: str = None
    mcp_bind_port: int = None

    def __post_init__(self):
        """Validate mcp configuration."""
        if not self.mcp_server_transport:
            raise ValueError("MCP SERVER TRANSPORT is required")
        if not self.mcp_bind_host:
            raise ValueError(f"MCP BIND HOST is required")
        if not self.mcp_bind_port:
            raise ValueError(f"MCP BIND PORT is required")

@dataclass
class PrometheusConfig:
    url: str
    url_ssl_verify: bool = True
    disable_prometheus_links: bool = False
    # Optional credentials
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    # Optional Org ID for multi-tenant setups
    org_id: Optional[str] = None
    # Optional Custom MCP Server Configuration
    mcp_server_config: Optional[MCPServerConfig] = None
    # Optional custom headers for Prometheus requests
    custom_headers: Optional[Dict[str, str]] = None
    # Request timeout in seconds to prevent hanging requests (DDoS protection)
    request_timeout: int = 30
    # Optional multi-tenant configuration
    tenants_raw: Optional[str] = None
    default_tenant_env: Optional[str] = None
    tenants: Optional[Dict[str, "TenantConfig"]] = None
    default_tenant: Optional[str] = None

@dataclass
class TenantConfig:
    name: str
    url: str
    url_ssl_verify: bool
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    org_id: Optional[str] = None
    custom_headers: Optional[Dict[str, str]] = None

config = PrometheusConfig(
    url=os.environ.get("PROMETHEUS_URL", ""),
    url_ssl_verify=os.environ.get("PROMETHEUS_URL_SSL_VERIFY", "True").lower() in ("true", "1", "yes"),
    disable_prometheus_links=os.environ.get("PROMETHEUS_DISABLE_LINKS", "False").lower() in ("true", "1", "yes"),
    username=os.environ.get("PROMETHEUS_USERNAME", ""),
    password=os.environ.get("PROMETHEUS_PASSWORD", ""),
    token=os.environ.get("PROMETHEUS_TOKEN", ""),
    org_id=os.environ.get("ORG_ID", ""),
    mcp_server_config=MCPServerConfig(
        mcp_server_transport=os.environ.get("PROMETHEUS_MCP_SERVER_TRANSPORT", "stdio").lower(),
        mcp_bind_host=os.environ.get("PROMETHEUS_MCP_BIND_HOST", "127.0.0.1"),
        mcp_bind_port=int(os.environ.get("PROMETHEUS_MCP_BIND_PORT", "8080"))
    ),
    custom_headers=json.loads(os.environ.get("PROMETHEUS_CUSTOM_HEADERS")) if os.environ.get("PROMETHEUS_CUSTOM_HEADERS") else None,
    request_timeout=int(os.environ.get("PROMETHEUS_REQUEST_TIMEOUT", "30")),
    tenants_raw=os.environ.get("PROMETHEUS_TENANTS", ""),
    default_tenant_env=os.environ.get("PROMETHEUS_DEFAULT_TENANT", ""),
)

def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return default

def _load_tenants(
    raw: Optional[str],
    default_tenant_env: Optional[str],
    base_url_ssl_verify: bool,
    base_custom_headers: Optional[Dict[str, str]]
) -> tuple[Dict[str, TenantConfig], Optional[str]]:
    if not raw:
        return {}, None

    try:
        tenants_data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid PROMETHEUS_TENANTS JSON: {exc}") from exc

    if not isinstance(tenants_data, list):
        raise ValueError("PROMETHEUS_TENANTS must be a JSON array of tenant objects")

    tenants: Dict[str, TenantConfig] = {}
    for idx, entry in enumerate(tenants_data):
        if not isinstance(entry, dict):
            raise ValueError(f"PROMETHEUS_TENANTS[{idx}] must be an object")

        name = entry.get("name")
        url = entry.get("url")
        if not name or not url:
            raise ValueError(f"PROMETHEUS_TENANTS[{idx}] requires 'name' and 'url'")
        if name in tenants:
            raise ValueError(f"Duplicate tenant name '{name}' in PROMETHEUS_TENANTS")

        tenant_custom_headers = entry.get("custom_headers")
        if tenant_custom_headers is not None and not isinstance(tenant_custom_headers, dict):
            raise ValueError(f"PROMETHEUS_TENANTS[{idx}].custom_headers must be an object")

        combined_headers = None
        if base_custom_headers or tenant_custom_headers:
            combined_headers = dict(base_custom_headers or {})
            if tenant_custom_headers:
                combined_headers.update(tenant_custom_headers)

        tenants[name] = TenantConfig(
            name=name,
            url=url,
            url_ssl_verify=_parse_bool(entry.get("url_ssl_verify"), base_url_ssl_verify),
            username=entry.get("username"),
            password=entry.get("password"),
            token=entry.get("token"),
            org_id=entry.get("org_id"),
            custom_headers=combined_headers
        )

    default_name = default_tenant_env or None
    if default_name:
        if default_name not in tenants:
            raise ValueError(f"PROMETHEUS_DEFAULT_TENANT '{default_name}' not found in PROMETHEUS_TENANTS")
    else:
        default_name = next(iter(tenants)) if tenants else None

    return tenants, default_name

def initialize_tenants() -> None:
    if not isinstance(config, PrometheusConfig):
        config.tenants = {}
        config.default_tenant = None
        return
    if isinstance(config.tenants, dict):
        return
    if not hasattr(config, "tenants_raw"):
        config.tenants = {}
        config.default_tenant = None
        return
    tenants, default_tenant = _load_tenants(
        config.tenants_raw,
        config.default_tenant_env,
        config.url_ssl_verify,
        config.custom_headers
    )
    config.tenants = tenants
    config.default_tenant = default_tenant

def _tenants_enabled() -> bool:
    return isinstance(config.tenants, dict) and len(config.tenants) > 0

def _resolve_tenant(tenant: Optional[str]) -> Optional[TenantConfig]:
    initialize_tenants()
    if not _tenants_enabled():
        return None
    selected = tenant or config.default_tenant
    if not selected:
        raise ValueError("No tenant specified and PROMETHEUS_DEFAULT_TENANT is not set")
    if selected not in config.tenants:
        raise ValueError(f"Unknown tenant '{selected}'. Available tenants: {', '.join(config.tenants.keys())}")
    return config.tenants[selected]

def get_prometheus_auth(
    username: Optional[str] = None,
    password: Optional[str] = None,
    token: Optional[str] = None
):
    """Get authentication for Prometheus based on provided credentials."""
    if username is None and password is None and token is None:
        username = config.username
        password = config.password
        token = config.token

    if token:
        return {"Authorization": f"Bearer {token}"}
    if username and password:
        return requests.auth.HTTPBasicAuth(username, password)
    return None

def _get_base_url(tenant: Optional[str]) -> str:
    tenant_config = _resolve_tenant(tenant)
    return tenant_config.url if tenant_config else config.url

def make_prometheus_request(endpoint, params=None, tenant: Optional[str] = None):
    """Make a request to the Prometheus API with proper authentication and headers."""
    tenant_config = _resolve_tenant(tenant)
    if not tenant_config and not config.url:
        logger.error("Prometheus configuration missing", error="PROMETHEUS_URL not set")
        raise ValueError("Prometheus configuration is missing. Please set PROMETHEUS_URL or PROMETHEUS_TENANTS.")

    url = _get_base_url(tenant)
    url_ssl_verify = tenant_config.url_ssl_verify if tenant_config else config.url_ssl_verify
    if not url_ssl_verify:
        logger.warning("SSL certificate verification is disabled. This is insecure and should not be used in production environments.", endpoint=endpoint)

    url = f"{url.rstrip('/')}/api/v1/{endpoint}"
    username = tenant_config.username if tenant_config else config.username
    password = tenant_config.password if tenant_config else config.password
    token = tenant_config.token if tenant_config else config.token
    auth = get_prometheus_auth(username, password, token)
    headers = {}

    if isinstance(auth, dict):  # Token auth is passed via headers
        headers.update(auth)
        auth = None  # Clear auth for requests.get if it's already in headers
    
    # Add OrgID header if specified
    org_id = tenant_config.org_id if tenant_config and tenant_config.org_id is not None else config.org_id
    if org_id:
        headers["X-Scope-OrgID"] = org_id

    custom_headers = tenant_config.custom_headers if tenant_config else config.custom_headers
    if custom_headers:
        headers.update(custom_headers)

    try:
        logger.debug("Making Prometheus API request", endpoint=endpoint, url=url, params=params, headers=headers, timeout=config.request_timeout)

        # Make the request with appropriate headers, auth, and timeout (DDoS protection)
        response = _session.get(url, params=params, auth=auth, headers=headers, verify=url_ssl_verify, timeout=config.request_timeout)

        response.raise_for_status()
        result = response.json()
        
        if result["status"] != "success":
            error_msg = result.get('error', 'Unknown error')
            logger.error("Prometheus API returned error", endpoint=endpoint, error=error_msg, status=result["status"])
            raise ValueError(f"Prometheus API error: {error_msg}")
        
        data_field = result.get("data", {})
        if isinstance(data_field, dict):
            result_type = data_field.get("resultType")
        else:
            result_type = "list"
        logger.debug("Prometheus API request successful", endpoint=endpoint, result_type=result_type)
        return result["data"]
    
    except requests.exceptions.RequestException as e:
        logger.error("HTTP request to Prometheus failed", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Prometheus response as JSON", endpoint=endpoint, url=url, error=str(e))
        raise ValueError(f"Invalid JSON response from Prometheus: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error during Prometheus request", endpoint=endpoint, url=url, error=str(e), error_type=type(e).__name__)
        raise

def _get_cache_key(tenant: Optional[str]) -> str:
    initialize_tenants()
    if _tenants_enabled():
        return tenant or config.default_tenant or "default"
    return "default"

def get_cached_metrics(tenant: Optional[str] = None) -> List[str]:
    """Get metrics list with caching to improve completion performance.

    This helper function is available for future completion support when
    FastMCP implements the completion capability. For now, it can be used
    internally to optimize repeated metric list requests.
    """
    current_time = time.time()
    cache_key = _get_cache_key(tenant)
    cache_entry = _metrics_cache.get(cache_key, {"data": None, "timestamp": 0})

    # Check if cache is valid
    if cache_entry["data"] is not None and (current_time - cache_entry["timestamp"]) < _CACHE_TTL:
        logger.debug("Using cached metrics list", cache_age=current_time - cache_entry["timestamp"], tenant=cache_key)
        return cache_entry["data"]

    # Fetch fresh metrics
    try:
        data = make_prometheus_request("label/__name__/values", tenant=tenant)
        _metrics_cache[cache_key] = {"data": data, "timestamp": current_time}
        logger.debug("Refreshed metrics cache", metric_count=len(data), tenant=cache_key)
        return data
    except Exception as e:
        logger.error("Failed to fetch metrics for cache", error=str(e))
        # Return cached data if available, even if expired
        return cache_entry["data"] if cache_entry["data"] is not None else []

# Note: Argument completions will be added when FastMCP supports the completion
# capability. The get_cached_metrics() function above is ready for that integration.

@mcp.tool(
    name=_tool_name("execute_query"),
    description="Execute a PromQL instant query against Prometheus (supports optional tenant selection)",
    annotations={
        "title": "Execute PromQL Query",
        "icon": "📊",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_query(query: str, time: Optional[str] = None, tenant: Optional[str] = None) -> Dict[str, Any]:
    """Execute an instant query against Prometheus.

    Args:
        query: PromQL query string
        time: Optional RFC3339 or Unix timestamp (default: current time)
        tenant: Optional tenant name when PROMETHEUS_TENANTS is configured

    Returns:
        Query result with type (vector, matrix, scalar, string) and values
    """
    params = {"query": query}
    if time:
        params["time"] = time
    
    logger.info("Executing instant query", query=query, time=time, tenant=tenant)
    data = make_prometheus_request("query", params=params, tenant=tenant)

    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        ui_params = {"g0.expr": query, "g0.tab": "0"}
        if time:
            ui_params["g0.moment_input"] = time
        prometheus_ui_link = f"{_get_base_url(tenant).rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "View in Prometheus UI"
        }]

    logger.info("Instant query completed",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1)

    return result

@mcp.tool(
    name=_tool_name("execute_range_query"),
    description="Execute a PromQL range query with start time, end time, and step interval (supports optional tenant selection)",
    annotations={
        "title": "Execute PromQL Range Query",
        "icon": "📈",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def execute_range_query(query: str, start: str, end: str, step: str, ctx: Context | None = None, tenant: Optional[str] = None) -> Dict[str, Any]:
    """Execute a range query against Prometheus.

    Args:
        query: PromQL query string
        start: Start time as RFC3339 or Unix timestamp
        end: End time as RFC3339 or Unix timestamp
        step: Query resolution step width (e.g., '15s', '1m', '1h')
        tenant: Optional tenant name when PROMETHEUS_TENANTS is configured

    Returns:
        Range query result with type (usually matrix) and values over time
    """
    params = {
        "query": query,
        "start": start,
        "end": end,
        "step": step
    }

    logger.info("Executing range query", query=query, start=start, end=end, step=step, tenant=tenant)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Initiating range query...")

    data = make_prometheus_request("query_range", params=params, tenant=tenant)

    # Report progress
    if ctx:
        await ctx.report_progress(progress=50, total=100, message="Processing query results...")

    result = {
        "resultType": data["resultType"],
        "result": data["result"]
    }

    if not config.disable_prometheus_links:
        from urllib.parse import urlencode
        ui_params = {
            "g0.expr": query,
            "g0.tab": "0",
            "g0.range_input": f"{start} to {end}",
            "g0.step_input": step
        }
        prometheus_ui_link = f"{_get_base_url(tenant).rstrip('/')}/graph?{urlencode(ui_params)}"
        result["links"] = [{
            "href": prometheus_ui_link,
            "rel": "prometheus-ui",
            "title": "View in Prometheus UI"
        }]

    # Report completion
    if ctx:
        await ctx.report_progress(progress=100, total=100, message="Range query completed")

    logger.info("Range query completed",
                query=query,
                result_type=data["resultType"],
                result_count=len(data["result"]) if isinstance(data["result"], list) else 1,
                tenant=tenant)

    return result

@mcp.tool(
    name=_tool_name("list_metrics"),
    description="List all available metrics in Prometheus with optional pagination support (supports optional tenant selection)",
    annotations={
        "title": "List Available Metrics",
        "icon": "📋",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def list_metrics(
    limit: Optional[int] = None,
    offset: int = 0,
    filter_pattern: Optional[str] = None,
    ctx: Context | None = None,
    tenant: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve a list of all metric names available in Prometheus.

    Args:
        limit: Maximum number of metrics to return (default: all metrics)
        offset: Number of metrics to skip for pagination (default: 0)
        filter_pattern: Optional substring to filter metric names (case-insensitive)
        tenant: Optional tenant name when PROMETHEUS_TENANTS is configured

    Returns:
        Dictionary containing:
        - metrics: List of metric names
        - total_count: Total number of metrics (before pagination)
        - returned_count: Number of metrics returned
        - offset: Current offset
        - has_more: Whether more metrics are available
    """
    logger.info("Listing available metrics", limit=limit, offset=offset, filter_pattern=filter_pattern, tenant=tenant)

    # Report progress if context available
    if ctx:
        await ctx.report_progress(progress=0, total=100, message="Fetching metrics list...")

    data = make_prometheus_request("label/__name__/values", tenant=tenant)

    if ctx:
        await ctx.report_progress(progress=50, total=100, message=f"Processing {len(data)} metrics...")

    # Apply filter if provided
    if filter_pattern:
        filtered_data = [m for m in data if filter_pattern.lower() in m.lower()]
        logger.debug("Applied filter", original_count=len(data), filtered_count=len(filtered_data), pattern=filter_pattern)
        data = filtered_data

    total_count = len(data)

    # Apply pagination
    start_idx = offset
    end_idx = offset + limit if limit is not None else len(data)
    paginated_data = data[start_idx:end_idx]

    result = {
        "metrics": paginated_data,
        "total_count": total_count,
        "returned_count": len(paginated_data),
        "offset": offset,
        "has_more": end_idx < total_count
    }

    if ctx:
        await ctx.report_progress(progress=100, total=100, message=f"Retrieved {len(paginated_data)} of {total_count} metrics")

    logger.info("Metrics list retrieved",
                total_count=total_count,
                returned_count=len(paginated_data),
                offset=offset,
                has_more=result["has_more"])

    return result

@mcp.tool(
    name=_tool_name("get_metric_metadata"),
    description="Get metadata for a specific metric (supports optional tenant selection)",
    annotations={
        "title": "Get Metric Metadata",
        "icon": "ℹ️",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_metric_metadata(metric: str, tenant: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get metadata about a specific metric.

    Args:
        metric: The name of the metric to retrieve metadata for
        tenant: Optional tenant name when PROMETHEUS_TENANTS is configured

    Returns:
        List of metadata entries for the metric
    """
    logger.info("Retrieving metric metadata", metric=metric, tenant=tenant)
    endpoint = f"metadata?metric={metric}"
    data = make_prometheus_request(endpoint, params=None, tenant=tenant)
    if "metadata" in data:
        metadata = data["metadata"]
    elif "data" in data:
        metadata = data["data"]
    else:
        metadata = data
    if isinstance(metadata, dict):
        metadata = [metadata]
    logger.info("Metric metadata retrieved", metric=metric, metadata_count=len(metadata))
    return metadata

@mcp.tool(
    name=_tool_name("get_targets"),
    description="Get information about all scrape targets (supports optional tenant selection)",
    annotations={
        "title": "Get Scrape Targets",
        "icon": "🎯",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def get_targets(tenant: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Get information about all Prometheus scrape targets.

    Args:
        tenant: Optional tenant name when PROMETHEUS_TENANTS is configured

    Returns:
        Dictionary with active and dropped targets information
    """
    logger.info("Retrieving scrape targets information", tenant=tenant)
    data = make_prometheus_request("targets", tenant=tenant)
    
    result = {
        "activeTargets": data["activeTargets"],
        "droppedTargets": data["droppedTargets"]
    }
    
    logger.info("Scrape targets retrieved", 
                active_targets=len(data["activeTargets"]), 
                dropped_targets=len(data["droppedTargets"]))
    
    return result

@mcp.tool(
    name=_tool_name("list_tenants"),
    description="List configured Prometheus tenants (if PROMETHEUS_TENANTS is set)",
    annotations={
        "title": "List Tenants",
        "icon": "🧭",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def list_tenants(include_urls: bool = False) -> Dict[str, Any]:
    """List configured tenants and the default tenant name.

    Args:
        include_urls: Include tenant URLs in the response (default: False)

    Returns:
        Dictionary containing:
        - tenants: List of tenant summaries (name, url?, url_ssl_verify, has_auth, has_org_id)
        - default_tenant: Default tenant name (if configured)
    """
    initialize_tenants()
    tenants = []
    if config.tenants:
        for tenant in config.tenants.values():
            has_auth = bool(tenant.token) or bool(tenant.username and tenant.password)
            summary = {
                "name": tenant.name,
                "url_ssl_verify": tenant.url_ssl_verify,
                "has_auth": has_auth,
                "has_org_id": bool(tenant.org_id)
            }
            if include_urls:
                summary["url"] = tenant.url
            tenants.append(summary)

    return {
        "tenants": tenants,
        "default_tenant": config.default_tenant
    }

if __name__ == "__main__":
    logger.info("Starting Prometheus MCP Server", mode="direct")
    mcp.run()
