"""Validated execution boundary between execution plans and MCP functions."""

import importlib
import inspect
from typing import Any

from _3__executor.mcp_tools.mcp_catalog import MCP_CATALOG, refresh_mcp_catalog


class MCPDispatchError(RuntimeError):
    pass


async def dispatch_mcp_action(action: str, arguments: dict[str, Any]) -> Any:
    if not action.startswith("mcp:"):
        raise MCPDispatchError(f"Không phải MCP action: {action}")
    qualified_name = action.removeprefix("mcp:").strip()
    if "." not in qualified_name:
        raise MCPDispatchError(f"MCP action không hợp lệ: {action}")
    mcp_name, tool_name = qualified_name.split(".", 1)

    refresh_mcp_catalog()
    if not any(tool.mcp_name == mcp_name and tool.tool_name == tool_name for tool in MCP_CATALOG):
        raise MCPDispatchError(f"MCP tool chưa được catalog: {qualified_name}")

    module = importlib.import_module(f"_3__executor.mcp_tools.{mcp_name}")
    function = getattr(module, tool_name, None)
    if not callable(function):
        raise MCPDispatchError(f"MCP implementation không có function: {qualified_name}")

    result = function(**arguments)
    if inspect.isawaitable(result):
        return await result
    return result
