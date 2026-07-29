"""Runtime-discovered catalog of the MCP tools available to the planner."""

from dataclasses import dataclass
import importlib
from pathlib import Path
import pkgutil
from typing import Any


@dataclass(frozen=True, slots=True)
class MCPToolSpec:
    """The intentionally small planner-facing schema."""

    mcp_name: str
    tool_name: str
    tool_description: str
    input_description: str
    output_description: str


# The list is refreshed at VM startup and immediately before rendering the
# planner prompt.  This makes adding/removing a local MCP visible without a
# database migration or a manually edited central registry.
MCP_CATALOG: list[MCPToolSpec] = []


def _tool_specs_from_module(module: Any, mcp_name: str) -> list[MCPToolSpec]:
    """Read metadata exposed by an MCP package's get_tools() hook."""

    get_tools = getattr(module, "get_tools", None)
    if not callable(get_tools):
        return []

    specs: list[MCPToolSpec] = []
    for raw_tool in get_tools() or ():
        if isinstance(raw_tool, MCPToolSpec):
            specs.append(raw_tool)
            continue
        if not isinstance(raw_tool, dict):
            continue
        tool_name = str(raw_tool.get("tool_name", raw_tool.get("name", ""))).strip()
        description = str(raw_tool.get("tool_description", raw_tool.get("description", ""))).strip()
        input_description = str(raw_tool.get("input_description", "")).strip()
        output_description = str(raw_tool.get("output_description", "")).strip()
        if tool_name and description and input_description and output_description:
            specs.append(
                MCPToolSpec(
                    mcp_name,
                    tool_name,
                    description,
                    input_description,
                    output_description,
                )
            )
    return specs


def refresh_mcp_catalog() -> tuple[MCPToolSpec, ...]:
    """Discover every ``*_mcp`` package below this directory."""

    package_dir = Path(__file__).resolve().parent
    discovered: list[MCPToolSpec] = []
    seen: set[tuple[str, str]] = set()

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if not module_info.name.endswith("_mcp"):
            continue
        module_name = f"mcp_tools.{module_info.name}"
        try:
            module = importlib.import_module(module_name)
            candidates = _tool_specs_from_module(module, module_info.name)
        except Exception:
            # A broken optional MCP must not prevent the VM from starting.
            continue
        for tool in candidates:
            key = (tool.mcp_name, tool.tool_name)
            if key not in seen:
                discovered.append(tool)
                seen.add(key)

    MCP_CATALOG.clear()
    MCP_CATALOG.extend(discovered)
    return tuple(MCP_CATALOG)


def render_for_planner() -> str:
    """Refresh and render the current catalog as a compact Markdown table."""

    refresh_mcp_catalog()
    if not MCP_CATALOG:
        return "(Chưa có MCP tool nào được đăng ký.)"

    lines = [
        "| mcp_name | tool_name | tool_description | input_description | output_description |",
        "|---|---|---|---|---|",
    ]
    for tool in MCP_CATALOG:
        cells = (
            tool.mcp_name,
            tool.tool_name,
            tool.tool_description,
            tool.input_description,
            tool.output_description,
        )
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines)


def catalog_as_rows() -> list[dict[str, str]]:
    """Return the discovered catalog for diagnostics or an admin endpoint."""

    refresh_mcp_catalog()
    return [
        {
            "mcp_name": tool.mcp_name,
            "tool_name": tool.tool_name,
            "tool_description": tool.tool_description,
            "input_description": tool.input_description,
            "output_description": tool.output_description,
        }
        for tool in MCP_CATALOG
    ]
