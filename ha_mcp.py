#!/usr/bin/env python3
"""Local MCP server for Home Assistant (stdio). Read-only by default.

Install:
  pip install "mcp[cli]"

Environment:
  HA_URL            e.g. http://192.168.1.50:8123   (required)
  HA_TOKEN          long-lived access token          (required)
  HA_MCP_ALLOW      comma-separated service patterns that enable control,
                    e.g. "light.*,climate.set_temperature,media_player.media_pause"
                    Unset/empty = observe-only; the control tool is not even registered.
  HA_MCP_ENTITIES   optional comma-separated entity patterns control may touch,
                    e.g. "light.living_room*,climate.*"  (default: any entity)

Sensitive domains (lock, cover, alarm_control_panel, valve, siren) need
confirm=true on every call, even when allowlisted.

Register with Claude Code:
  claude mcp add home-assistant \
    -e HA_URL=http://<ip>:8123 -e HA_TOKEN=<token> \
    -- python3 /path/to/ha_mcp.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from fnmatch import fnmatch

from mcp.server.fastmcp import FastMCP

URL = os.environ.get("HA_URL", "").rstrip("/")
TOKEN = os.environ.get("HA_TOKEN", "")
ALLOW = [p.strip() for p in os.environ.get("HA_MCP_ALLOW", "").split(",") if p.strip()]
ENTITY_ALLOW = [
    p.strip() for p in os.environ.get("HA_MCP_ENTITIES", "*").split(",") if p.strip()
]
SENSITIVE_DOMAINS = {"lock", "cover", "alarm_control_panel", "valve", "siren"}

if not URL or not TOKEN:
    sys.exit("HA_URL and HA_TOKEN must be set.")

mcp = FastMCP("home-assistant")


def _request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{URL}/api/{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Home Assistant returned HTTP {e.code} for {path}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Home Assistant at {URL}: {e.reason}") from e


# ---------------------------------------------------------------- observe ---


@mcp.tool()
def ha_summary() -> str:
    """Count of entities per domain (light, sensor, switch, ...)."""
    states = _request("GET", "states")
    counts = Counter(s["entity_id"].split(".")[0] for s in states)
    lines = [f"{len(states)} entities"]
    lines += [f"{d}: {n}" for d, n in counts.most_common()]
    return "\n".join(lines)


@mcp.tool()
def ha_list_entities(domain: str = "", limit: int = 100) -> str:
    """List entities with state and friendly name. Optionally filter by domain
    (e.g. 'light', 'sensor'). Returns at most `limit` rows."""
    states = _request("GET", "states")
    rows = []
    for s in sorted(states, key=lambda s: s["entity_id"]):
        if domain and not s["entity_id"].startswith(domain + "."):
            continue
        name = s["attributes"].get("friendly_name", "")
        unit = s["attributes"].get("unit_of_measurement", "")
        rows.append(f"{s['entity_id']} | {s['state']}{unit} | {name}")
    shown = rows[:limit]
    if len(rows) > limit:
        shown.append(f"... {len(rows) - limit} more (raise limit or filter by domain)")
    return "\n".join(shown) or "No matching entities."


@mcp.tool()
def ha_get_state(entity_id: str) -> str:
    """Full state and attributes for one entity."""
    return json.dumps(_request("GET", f"states/{entity_id}"), indent=2)


@mcp.tool()
def ha_history(entity_id: str, hours: int = 24) -> str:
    """Compact state history for one entity over the last N hours (max 168)."""
    from datetime import datetime, timedelta, timezone

    hours = max(1, min(hours, 168))
    start = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    start = start.replace("+", "%2B")
    data = _request(
        "GET",
        f"history/period/{start}?filter_entity_id={entity_id}"
        "&minimal_response&no_attributes",
    )
    if not data or not data[0]:
        return "No history."
    return "\n".join(
        f"{p.get('last_changed', '')[:19]}  {p['state']}" for p in data[0][:200]
    )


# ---------------------------------------------------------------- control ---
# Registered only when HA_MCP_ALLOW is set.


def _service_allowed(domain: str, service: str) -> bool:
    full = f"{domain}.{service}"
    return any(fnmatch(full, pat) for pat in ALLOW)


def _entity_allowed(entity_id: str) -> bool:
    return any(fnmatch(entity_id, pat) for pat in ENTITY_ALLOW)


if ALLOW:

    @mcp.tool()
    def ha_call_service(
        domain: str,
        service: str,
        entity_id: str,
        data: dict | None = None,
        confirm: bool = False,
    ) -> str:
        """Call a Home Assistant service on ONE entity, e.g. domain='light',
        service='turn_on', entity_id='light.desk', data={'brightness_pct': 40}.
        Only allowlisted services/entities work. Sensitive domains (lock, cover,
        alarm_control_panel, valve, siren) require confirm=true, which should only
        be set after the user has explicitly approved that specific action."""
        if not _service_allowed(domain, service):
            return f"Blocked: {domain}.{service} is not in the allowlist."
        if not _entity_allowed(entity_id):
            return f"Blocked: {entity_id} is not in the entity allowlist."
        if not entity_id.startswith(domain + ".") and domain != "homeassistant":
            return f"Blocked: {entity_id} does not belong to domain '{domain}'."
        if domain in SENSITIVE_DOMAINS and not confirm:
            return (
                f"Needs confirmation: {domain}.{service} on {entity_id} is a "
                "sensitive action. Ask the user, then retry with confirm=true."
            )
        body = dict(data or {})
        body["entity_id"] = entity_id  # single entity only; no lists or 'all'
        result = _request("POST", f"services/{domain}/{service}", body)
        return f"OK: {domain}.{service} on {entity_id}. Changed: {len(result)} entity state(s)."


if __name__ == "__main__":
    mcp.run()
