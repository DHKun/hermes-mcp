# hermes-mcp

<!-- language picker -->
[English](./README.md) | [简体中文](./README_zh.md)

> Expose Hermes Agent tools to Claude Code via MCP (Model Context Protocol)

Turn your Hermes Agent into an MCP server so Claude Code can call its tools (browser automation, terminal, file read/write, vision, etc.) directly — no `delegate_task` overhead, just native MCP integration.

## Architecture

```
Claude Code (MCP Client) ←→ hermes-mcp-server.py ←→ Hermes tools
                                (stdio)            (terminal, browser, etc.)
```

Without this: Claude Code has limited built-in tools and can't access Hermes capabilities.

With this: Claude Code gets **34 Hermes tools** as first-class MCP tools.

## What You Get

| Category | Tools |
|----------|-------|
| Browser | `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_scroll`, `browser_vision`, `browser_console`, ... |
| Terminal | `terminal`, `process` |
| File | `read_file`, `write_file`, `patch`, `search_files` |
| Web | `web_search`, `web_extract` |
| Vision | `vision_analyze` |
| Skills | `skills_list`, `skill_view`, `skill_manage` |
| Code | `execute_code`, `delegate_task` |
| Memory | `memory`, `session_search` |
| Other | `todo`, `clarify`, `cronjob`, `text_to_speech`, `homeassistant` |

## Prerequisites

1. **Hermes Agent** installed at `~/.hermes/hermes-agent`
2. **MCP SDK for Python**:
   ```bash
   cd ~/.hermes/hermes-agent
   uv pip install mcp --python .venv/bin/python3
   ```
3. **Claude Code v2.x** with MCP support

## Quick Start

### Step 1: Install the MCP server

```bash
# Clone the repo
git clone https://github.com/DHKun/hermes-mcp.git
cd hermes-mcp

# Or just copy the script anywhere
cp hermes-mcp-server.py ~/.hermes/
chmod +x hermes-mcp-server.py
```

### Step 2: Connect to Claude Code

```bash
# Via CLI (easiest)
claude mcp add hermes -- python /path/to/hermes-mcp-server.py

# Verify it works
claude mcp list
# Should show: hermes → python ... hermes-mcp-server.py
```

### Step 3: Use Hermes tools in Claude Code

Once connected, Claude Code can naturally call Hermes tools:

```
# Open a browser and navigate
Use browser_navigate to check https://github.com/trending

# Run terminal commands with full context
Use terminal to run git status and git diff

# Read/write files with Hermes path handling
Use read_file to look at src/app.py
Use patch to add error handling to src/app.py

# Search across codebase
Use search_files to find all uses of "async def"

# Delegate complex tasks back to Hermes Agent
Use delegate_task with goal="Research the architecture of this repo"
```

Claude Code will automatically see Hermes tools alongside its native tools — no special syntax needed.

## Configuration

### Option A: Via Claude Code CLI (easiest)

```bash
claude mcp add hermes -- python /path/to/hermes-mcp-server.py
```

### Option B: Via settings.json (persistent)

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"]
    }
  }
}
```

### Option C: Per-project (team-shared)

Add to `.claude/settings.json` in your project:

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"]
    }
  }
}
```

## How It Works

1. The MCP server (`hermes-mcp-server.py`) imports Hermes's tool registry at startup
2. It registers all Hermes tools as MCP tools with their full schemas
3. When Claude Code calls a tool, the server forwards it to Hermes's handler
4. Results are JSON-serialized and returned via stdio

The server uses stdio transport — the most reliable for local subprocess communication:
- No port conflicts
- No network overhead
- Works in all environments (local, SSH, Docker)
- Natural for Claude Code's subprocess model

## Security

- The server runs as a subprocess of Claude Code, inheriting its environment (ANTHROPIC_API_KEY, etc.)
- It does **not** expose Hermes's messaging adapters (Telegram, Discord)
- Large outputs are truncated at 200K chars (configurable via `HERMES_MCP_MAX_OUTPUT`)
- No credentials are leaked — only tool results are returned

## Troubleshooting

### "MCP server hermes failed to start"

Check the Python path — you must use the same Python that has the `mcp` package installed:

```bash
# Wrong (system Python may not have mcp)
python hermes-mcp-server.py

# Right (use Hermes's venv Python)
~/.hermes/hermes-agent/.venv/bin/python3 hermes-mcp-server.py
```

### "Tool not found" errors

Claude Code may have cached old tool definitions. Restart the MCP server:

```bash
claude mcp remove hermes
claude mcp add hermes -- python /path/to/hermes-mcp-server.py
```

### Very large outputs

Set `HERMES_MCP_MAX_OUTPUT` env var:

```json
{
  "mcpServers": {
    "hermes": {
      "command": "python",
      "args": ["/path/to/hermes-mcp-server.py"],
      "env": { "HERMES_MCP_MAX_OUTPUT": "500000" }
    }
  }
}
```

## Comparison with `delegate_task`

| Aspect | `delegate_task` | `hermes-mcp` |
|--------|----------------|--------------|
| Startup | Spawns new subprocess per task | One persistent server |
| Latency | ~1-2s overhead per call | Near-zero (in-process) |
| Tool access | Via Hermes CLI parsing | Direct MCP calls |
| Best for | One-shot complex tasks | Fast, frequent tool calls |
| Session continuity | Each task is fresh | Server persists in session |

For code writing/refactoring: `hermes-mcp` is faster.

For delegation to full agent with full context: `delegate_task` is still appropriate.

## License

MIT
