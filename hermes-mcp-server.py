#!/usr/bin/env python3
"""
Hermes MCP Server — exposes Hermes Agent tools to Claude Code via stdio

This script runs as a stdio MCP server, allowing Claude Code (or any MCP client)
to call Hermes tools (terminal, file read/write, browser, etc.) directly.

Usage:
    python hermes-mcp-server.py  # Run standalone

Claude Code config (~/.claude/settings.json):
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"]
    }
  }
}

Or via CLI:
    claude mcp add hermes -- python /path/to/hermes-mcp-server.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add hermes-agent to path
# Use HERMES_AGENT_ROOT env var if set, otherwise infer from script location
# Script is typically at: ~/.hermes/skills/autonomous-ai-agents/claude-code/scripts/hermes-mcp-server.py
# Herme-agent root is: ~/.hermes/hermes-agent/
AGENT_ROOT = Path(os.environ.get(
    "HERMES_AGENT_ROOT",
    Path(__file__).resolve().parent.parent.parent  # scripts → claude-code → skills → ~/.hermes
))
HERMES_AGENT_PATH = AGENT_ROOT / "hermes-agent"
sys.path.insert(0, str(HERMES_AGENT_PATH))

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, CallToolResult, ServerCapabilities, ToolsCapability
from mcp.server.models import InitializationOptions

# Import Hermes internals
from tools.registry import registry
import importlib

# ── Constants ────────────────────────────────────────────────────────────────

SERVER_NAME = "hermes"


# ── Hermes Tool → MCP Tool conversion ──────────────────────────────────────

def _discover_hermes_tools():
    """Import all Hermes tool modules to trigger registry.register() calls."""
    _modules = [
        "tools.web_tools", "tools.terminal_tool", "tools.file_tools",
        "tools.vision_tools", "tools.skills_tool", "tools.skill_manager_tool",
        "tools.browser_tool", "tools.cronjob_tools", "tools.tts_tool",
        "tools.todo_tool", "tools.memory_tool", "tools.session_search_tool",
        "tools.clarify_tool", "tools.code_execution_tool", "tools.delegate_tool",
        "tools.process_registry", "tools.send_message_tool", "tools.homeassistant_tool",
    ]
    for mod_name in _modules:
        try:
            importlib.import_module(mod_name)
        except Exception as e:
            print(f"[hermes-mcp] skipped {mod_name}: {e}", file=sys.stderr)


def _build_hermes_tools() -> list[Tool]:
    """Discover all Hermes tools and convert to MCP Tool format."""
    _discover_hermes_tools()

    # Toolsets to SKIP — internal/adapter tools not useful for Claude Code
    SKIP_TOOLSETS = {"messaging"}

    hermes_tools = []
    for name, entry in registry._tools.items():
        if entry.toolset in SKIP_TOOLSETS:
            continue

        schema = entry.schema
        params = schema.get("parameters", {})

        # Convert JSON Schema to MCP input schema
        input_schema = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        param_props = params.get("properties", {})
        for pname, pval in param_props.items():
            prop = {"type": pval.get("type", "string")}
            if "description" in pval:
                prop["description"] = pval["description"]
            if "default" in pval:
                prop["default"] = pval["default"]
            if "enum" in pval:
                prop["enum"] = pval["enum"]
            input_schema["properties"][pname] = prop

        # Handle required array
        required_list = params.get("required", [])
        if isinstance(required_list, list):
            input_schema["required"] = required_list

        if not params.get("additionalProperties", True):
            input_schema["additionalProperties"] = False

        # Trim description for MCP
        description = entry.description or schema.get("description", f"Call {name}")
        if len(description) > 2000:
            description = description[:2000] + "..."

        hermes_tools.append(Tool(
            name=name,
            description=description,
            inputSchema=input_schema,
        ))

    return hermes_tools


# ── MCP Server ───────────────────────────────────────────────────────────────

# Build tool list at module load
_hermes_tool_list: list[Tool] = []
_hermes_tool_map: dict[str, Tool] = {}


def _refresh_tools():
    global _hermes_tool_list, _hermes_tool_map
    _hermes_tool_list = _build_hermes_tools()
    _hermes_tool_map = {t.name: t for t in _hermes_tool_list}
    print(f"[hermes-mcp] loaded {len(_hermes_tool_list)} tools", file=sys.stderr)


_refresh_tools()

server = Server(SERVER_NAME)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available Hermes tools as MCP tools."""
    return _hermes_tool_list


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    """
    Handle a tool call from an MCP client (e.g. Claude Code).

    Raises errors for unknown tools or handler failures.
    Results are JSON-serialized and returned as text content.
    Large outputs are truncated at HERMES_MCP_MAX_OUTPUT (default 200K chars).
    """
    entry = registry._tools.get(name)
    if not entry:
        return CallToolResult(isError=True, content=[
            {"type": "text", "text": json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)}
        ])

    try:
        result = entry.handler(arguments)

        try:
            parsed = json.loads(result)
            if isinstance(parsed, dict) and "error" in parsed:
                return CallToolResult(isError=True, content=[
                    {"type": "text", "text": json.dumps(parsed, ensure_ascii=False)}
                ])
            text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            text = str(result)

        # Truncate very large outputs
        max_chars = int(os.environ.get("HERMES_MCP_MAX_OUTPUT", 200_000))
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [output truncated at {max_chars} chars]"

        return CallToolResult(isError=False, content=[
            {"type": "text", "text": text}
        ])

    except Exception as exc:
        return CallToolResult(isError=True, content=[
            {"type": "text", "text": json.dumps({"error": str(exc)}, ensure_ascii=False)}
        ])


# ── Main entry point ────────────────────────────────────────────────────────

async def main():
    """Start the Hermes MCP server (stdio transport)."""
    options = InitializationOptions(
        server_name=SERVER_NAME,
        server_version="1.0.0",
        capabilities=ServerCapabilities(
            tools=ToolsCapability(listChanged=True),
        ),
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            options,
            raise_exceptions=True,
        )


if __name__ == "__main__":
    anyio.run(main)
