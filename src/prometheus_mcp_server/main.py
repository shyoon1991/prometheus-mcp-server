#!/usr/bin/env python
import sys
import dotenv
from prometheus_mcp_server import server as server_module
from prometheus_mcp_server.server import mcp, config, TransportType, initialize_tenants
from prometheus_mcp_server.logging_config import setup_logging

# Initialize structured logging
logger = setup_logging()

def setup_environment():
    if dotenv.load_dotenv():
        logger.info("Environment configuration loaded", source=".env file")
    else:
        logger.info("Environment configuration loaded", source="environment variables", note="No .env file found")

    if config is server_module.config:
        try:
            initialize_tenants()
        except ValueError as exc:
            logger.error(
                "Invalid multi-tenant configuration",
                error=str(exc),
                suggestion="Fix PROMETHEUS_TENANTS / PROMETHEUS_DEFAULT_TENANT and restart"
            )
            return False

    if not config.tenants and not config.url:
        logger.error(
            "Missing required configuration",
            error="Neither PROMETHEUS_URL nor PROMETHEUS_TENANTS is set",
            suggestion="Set PROMETHEUS_URL or provide PROMETHEUS_TENANTS JSON",
            example="http://your-prometheus-server:9090"
        )
        return False

    if config.tenants:
        logger.info(
            "Multi-tenant configuration detected",
            tenant_count=len(config.tenants),
            default_tenant=config.default_tenant
        )
    
    # MCP Server configuration validation
    mcp_config = config.mcp_server_config
    if mcp_config:
        if str(mcp_config.mcp_server_transport).lower() not in TransportType.values():
            logger.error(
                "Invalid mcp transport",
                error="PROMETHEUS_MCP_SERVER_TRANSPORT environment variable is invalid",
                suggestion="Please define one of these acceptable transports (http/sse/stdio)",
                example="http"
            )
            return False

        try:
            if mcp_config.mcp_bind_port:
                int(mcp_config.mcp_bind_port)
        except (TypeError, ValueError):
            logger.error(
                "Invalid mcp port",
                error="PROMETHEUS_MCP_BIND_PORT environment variable is invalid",
                suggestion="Please define an integer",
                example="8080"
            )
            return False
    
    # Determine authentication method (default tenant or single-tenant)
    auth_method = "none"
    if config.tenants and config.default_tenant:
        default_tenant = config.tenants[config.default_tenant]
        if default_tenant.username and default_tenant.password:
            auth_method = "basic_auth"
        elif default_tenant.token:
            auth_method = "bearer_token"
    else:
        if config.username and config.password:
            auth_method = "basic_auth"
        elif config.token:
            auth_method = "bearer_token"
    
    logger.info(
        "Prometheus configuration validated",
        server_url=config.url if not config.tenants else None,
        authentication=auth_method,
        org_id=config.org_id if config.org_id else None,
        default_tenant=config.default_tenant if config.tenants else None
    )
    
    return True

def run_server():
    """Main entry point for the Prometheus MCP Server"""
    # Setup environment
    if not setup_environment():
        logger.error("Environment setup failed, exiting")
        sys.exit(1)
    
    mcp_config = config.mcp_server_config
    transport = mcp_config.mcp_server_transport

    http_transports = [TransportType.HTTP.value, TransportType.SSE.value]
    if transport in http_transports:
        mcp.run(transport=transport, host=mcp_config.mcp_bind_host, port=mcp_config.mcp_bind_port)
        logger.info("Starting Prometheus MCP Server", 
                transport=transport, 
                host=mcp_config.mcp_bind_host,
                port=mcp_config.mcp_bind_port)
    else:
        mcp.run(transport=transport)
        logger.info("Starting Prometheus MCP Server", transport=transport)

if __name__ == "__main__":
    run_server()
