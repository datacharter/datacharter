"""MCP (Model Context Protocol) server — governed query tools over stdio and HTTP."""

from datacharter.mcp.http import attach_mcp_routes, create_mcp_http_app, mcp_http_url
from datacharter.mcp.server import handle_message, mcp_tool_defs, serve_stdio

__all__ = [
    "handle_message",
    "mcp_tool_defs",
    "serve_stdio",
    "attach_mcp_routes",
    "create_mcp_http_app",
    "mcp_http_url",
]
