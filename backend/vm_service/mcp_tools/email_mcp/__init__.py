"""Email MCP metadata and implementation entry points."""

from .server import check_email, get_tools, search_email, send_email

__all__ = ["get_tools", "send_email", "check_email", "search_email"]
