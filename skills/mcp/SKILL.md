---
name: mcp
description: "Connect to MCP (Model Context Protocol) servers and use their external tools"
triggers:
  - mcp
  - model context protocol
  - mcp server
  - mcp tool
  - connect server
  - external tool
  - mcp connect
  - mcp disconnect
  - list mcp
tools:
  - mcp_connect
  - mcp_disconnect
  - mcp_list_servers
  - mcp_list_tools
  - mcp_call_tool
  - mcp_add_server
  - mcp_remove_server
  - memory_search
priority: 60
---

# MCP (Model Context Protocol) — External Tool Integration

MCP lets you connect to external servers that provide additional tools (filesystem, databases, APIs, browser automation, etc.) using the open Model Context Protocol standard.

## Available Tools

| Tool | Purpose |
|------|---------|
| `mcp_list_servers` | List all configured MCP servers and their connection status |
| `mcp_connect` | Connect to a configured server by name |
| `mcp_disconnect` | Disconnect from a running server |
| `mcp_list_tools` | List tools available from connected servers (optionally filter by server) |
| `mcp_call_tool` | Execute a tool on a connected server |
| `mcp_add_server` | Add a new MCP server config (persists to config, auto-connects) |
| `mcp_remove_server` | Remove a server (disconnects and deletes from config) |

## Workflow

### Using existing servers
1. **Check what's available**: `mcp_list_servers` — see configured servers and which are connected
2. **Connect**: `mcp_connect(server_name='<name>')` — starts the server process and discovers its tools
3. **Discover tools**: `mcp_list_tools(server_name='<name>')` — see what the server offers
4. **Use tools**: `mcp_call_tool(server_name='<name>', tool_name='<tool>', arguments={...})`
5. **Disconnect when done**: `mcp_disconnect(server_name='<name>')` — clean shutdown

### Adding new servers
1. **Add and connect**: `mcp_add_server(name='my-server', command='npx', args=['-y', 'package-name'])`
   - Persists to config.json so it survives restarts
   - Auto-connects and discovers tools immediately
2. **Remove if no longer needed**: `mcp_remove_server(name='my-server')`

## Key Rules

- Enabled servers auto-connect when Ghost starts and auto-reconnect if they crash
- Each server runs as a subprocess communicating over JSON-RPC (stdin/stdout)
- Tool access control: servers can define `allowed_tools` (whitelist) or `blocked_tools` (blacklist)
- Connections have a configurable timeout (default 30s) for each request
- You can add new servers at runtime — they persist to config and survive restarts

## Example: Adding and Using a Filesystem MCP Server

```
1. mcp_add_server(name="filesystem", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
   → {ok: true, server: "filesystem", connect_result: {ok: true, tools: [...]}}

2. mcp_list_tools(server_name="filesystem")
   → {ok: true, tools: [{name: "read_file", ...}, {name: "write_file", ...}]}

3. mcp_call_tool(server_name="filesystem", tool_name="read_file", arguments={"path": "/tmp/data.txt"})
   → {ok: true, result: {content: "file contents here..."}}
```

## Popular MCP Servers

| Server | Command | Args |
|--------|---------|------|
| Filesystem | `npx` | `-y @modelcontextprotocol/server-filesystem /path` |
| GitHub | `npx` | `-y @modelcontextprotocol/server-github` (needs `GITHUB_PERSONAL_ACCESS_TOKEN` env) |
| SQLite | `npx` | `-y @modelcontextprotocol/server-sqlite /path/to/db.sqlite` |
| Brave Search | `npx` | `-y @modelcontextprotocol/server-brave-search` (needs `BRAVE_API_KEY` env) |
| PostgreSQL | `npx` | `-y @modelcontextprotocol/server-postgres postgresql://...` |

## Configuration

Each server config supports: `command`, `args`, `env`, `enabled`, `timeout`, `allowed_tools`, `blocked_tools`.
