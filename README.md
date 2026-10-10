# Home Assistant MCP Server

Completely Claude-AI generated for integrating Claude with a local Home Assistant server.

This is a complete and utter experiment with "vibing" something to mess around with.

It's set up to be run via `uv`.

By default, the MCP server does **not** save any data and starts in "read only" mode (no commands).

## Claude config changes

Add this to your local Claude `config`:

```json
  "mcpServers": {
    "home-assistant": {
      "command": "<UV_PATH>/uv",
      "args": [
        "run",
        "--directory", "<PROJECT_PATH>/ha-mcp",
        "ha_mcp.py"
      ],
      "env": {
        "HA_URL": "http://<HA_URL>:8123",
        "HA_TOKEN": "<HA_TOKEN>"
      }
    }
  }

```

## Getting the token

1. Log in as the user you want the token for. For the observe-first setup, that’s the non-admin user you created for this, because the token carries that user’s permissions.
2. Open your profile by clicking your name or avatar at the bottom of the left sidebar.
3. Go to the Security tab at the top of the profile page.
4. Scroll to “Long-lived access tokens” at the bottom and click Create token.
5. Name it something like claude-mcp so you can recognize it later, then confirm.
6. Copy the token right away. Home Assistant shows it only once. If you lose it, you have to delete it and create a new one.

## Enabling control

The server is **observe-only by default**. The write tool (`ha_call_service`) is not even registered until you set `HA_MCP_ALLOW`. Two environment variables control what it may do:

### `HA_MCP_ALLOW`

Comma-separated patterns of services that control may call, in `domain.service` form. Wildcards (`*`) are supported. If unset or empty, control stays disabled.

```
HA_MCP_ALLOW="light.*,climate.set_temperature,media_player.media_pause"
```

### `HA_MCP_ENTITIES`

Optional comma-separated patterns limiting which entities those services may act on. Defaults to `*` (any entity). Use it to narrow a broad service allowlist to specific rooms or devices.

```
HA_MCP_ENTITIES="light.living_room*,climate.*"
```

A call must match both lists: the service must match `HA_MCP_ALLOW` and the entity must match `HA_MCP_ENTITIES`. Anything else is refused.

Other safeguards:
- Each call acts on a single named entity (no lists or "all").
- Sensitive domains (locks, covers such as garage doors, alarm panels, valves, and sirens) always require an explicit confirmation step, even when allowlisted. The server refuses the first attempt and asks for approval, and the action only goes through after you have approved that specific action.

Set these in the `env` block of the Claude Desktop config, then fully restart Desktop:

```json
"env": {
  "HA_URL": "http://<ha-ip>:8123",
  "HA_TOKEN": "<long-lived token>",
  "HA_MCP_ALLOW": "light.*",
  "HA_MCP_ENTITIES": "light.living_room*"
}
```
