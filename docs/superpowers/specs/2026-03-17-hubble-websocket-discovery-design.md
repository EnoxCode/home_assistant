# Hubble Integration: WebSocket & Discovery

**Date:** 2026-03-17
**Branch:** hubble-integration
**Status:** Approved

---

## Overview

Replace the 30-second REST poll with a WebSocket-push architecture for real-time entity updates (`page:changed`, `notification`, `notification:dismissed`). Add a discovery call (`GET /api/ws/events`) on boot that stores richer module data and drives conditional module entity creation. Keep a 5-minute REST resync as a fallback.

---

## 1. Data Layer

### 1.1 Discovery

A new `async_discover()` method on `HubbleApiClient` calls `GET /api/ws/events` and returns the raw discovery payload:

```python
async def async_discover(self) -> dict[str, Any]:
    """Call GET /api/ws/events and return the discovery payload."""
```

Response shape (relevant fields):
```json
{
  "core": {
    "events": [
      {"event": "page:changed", ...},
      {"event": "notification", ...}
    ]
  },
  "modules": [
    {
      "module": "hubble-timer",
      "version": "1.2.3",
      "events": [...],
      "endpoints": [...],
      "instances": [...]
    }
  ]
}
```

Discovery is called once in `async_setup_entry`, before the coordinator is created. If it fails, raise `ConfigEntryNotReady`. The result is stored as `coordinator.discovery: dict[str, Any]`.

`async_get_modules()` is removed from `api.py` — superseded by the richer discovery response. The `"modules"` key is removed from `coordinator.data`.

### 1.2 Coordinator data

The coordinator gather becomes a 2-call REST resync (5-minute interval):

```python
state, notify_count = await asyncio.gather(
    self.client.async_get_state(),
    self.client.async_get_notify_count(),
)
return {**state, "notificationCount": notify_count}
```

WebSocket events patch `coordinator.data` immediately via `async_set_updated_data()`:

| WebSocket event | Patch applied to coordinator data |
|---|---|
| `page:changed` | `activePage`, `pages`, `widgets` from event payload |
| `notification` | `notificationCount += 1` |
| `notification:dismissed` | `notificationCount = max(0, notificationCount - 1)` |

The REST resync provides ground-truth correction for any missed WebSocket events.

### 1.3 Module count sensor

`HubbleModuleCountSensor` switches from reading `coordinator.data["modules"]` to `coordinator.discovery.get("modules", [])`. The module count reflects what was discovered at boot and is static until the entry reloads.

---

## 2. WebSocket Client (`websocket.py`)

New file. `HubbleWebSocketClient` owns the connection lifecycle. It does not retry — the coordinator controls reconnect timing.

### 2.1 Interface

```python
class HubbleWebSocketClient:
    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
        on_event: Callable[[str, dict], None],
    ) -> None: ...

    async def async_connect(self) -> None:
        """Open connection, authenticate, send initial subscribe."""

    async def async_listen(self) -> None:
        """Receive loop. Returns when connection closes. Raises HubbleConnectionError on error."""

    async def async_disconnect(self) -> None:
        """Close connection cleanly."""

    async def async_add_subscription(
        self,
        *,
        events: list[str] | None = None,
        modules: list[str] | None = None,
        module_topics: list[str] | None = None,
    ) -> None:
        """Send {"action": "add", ...} and update internal subscription state."""
```

`on_event` signature: `(event_name: str, data: dict) -> None`

### 2.2 Subscription state

The client tracks accumulated subscriptions internally:

```python
_subscriptions: dict[str, set[str]] = {
    "events": {"page:changed", "notification", "notification:dismissed"},
    "modules": set(),
    "moduleTopics": set(),
}
```

`async_add_subscription` appends to these sets and sends `{"action": "add", ...}` to the live connection.

On reconnect, `async_connect` sends a single `subscribe` message built from the full `_subscriptions` state — this is correct per the protocol (a new connection starts fresh, so `subscribe` replaces rather than `add`).

### 2.3 Connection flow

```
async_connect():
  1. ws = await session.ws_connect(f"ws://{host}:{port}/ws")
  2. send {"action": "auth", "apiKey": api_key}
  3. recv → if {"error": ...} raise HubbleAuthError
             if {"authenticated": true} continue
  4. send {"action": "subscribe", "events": [...], "modules": [...], "moduleTopics": [...]}
     (built from _subscriptions, omitting empty sets)

async_listen():
  loop:
    msg = await ws.receive()
    if msg.type == WSMsgType.TEXT:
        parsed = json.loads(msg.data)
        on_event(parsed.get("event", ""), parsed.get("data", {}))
    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR):
        break
  # returns normally — coordinator decides whether to reconnect
```

### 2.4 Error handling

| Condition | Behaviour |
|---|---|
| HTTP 401 on WS upgrade | Raise `HubbleAuthError` |
| `{"error": ...}` auth response | Raise `HubbleAuthError` |
| `aiohttp.ClientError` on connect | Raise `HubbleConnectionError` |
| `WSMsgType.ERROR` in receive loop | Raise `HubbleConnectionError` |
| `WSMsgType.CLOSE` / `CLOSED` | Return normally (coordinator reconnects) |

---

## 3. Coordinator Changes (`coordinator.py`)

### 3.1 New attributes

```python
discovery: dict[str, Any]          # set by async_setup_entry before first refresh
ws_client: HubbleWebSocketClient | None = None
_module_handlers: dict[tuple[str, str], Callable[[dict], None]]
_ws_reconnect_task: asyncio.Task | None = None
```

### 3.2 Update interval

`SCAN_INTERVAL` changes from 30 seconds to 5 minutes (`timedelta(minutes=5)`).

### 3.3 Module infrastructure

```python
def is_module_discovered(self, module_name: str) -> bool:
    """Return True if module_name appears in discovery data."""
    return any(
        m["module"] == module_name
        for m in self.discovery.get("modules", [])
    )

def register_module_handler(
    self,
    module_name: str,
    topic: str,
    handler: Callable[[dict], None],
) -> None:
    """Register a callback for a module:data event."""
    self._module_handlers[(module_name, topic)] = handler
```

### 3.4 WebSocket event routing

```python
def _handle_ws_event(self, event: str, data: dict) -> None:
    """Route incoming WebSocket event to the correct handler."""
    if event == "module:data":
        module = data.get("module", "")
        topic = data.get("topic", "")
        handler = self._module_handlers.get((module, topic))
        if handler:
            handler(data.get("data", {}))
        else:
            _LOGGER.debug("Unhandled module:data event: %s:%s", module, topic)
        return

    # Core events
    current = dict(self.data) if self.data else {}
    match event:
        case "page:changed":
            current["activePage"] = data.get("activePage", current.get("activePage"))
            current["pages"] = data.get("page", current.get("pages"))  # note: page:changed sends single page object — use activePage + existing pages list, update only if full pages list present
            if "widgets" in data:
                current["widgets"] = data["widgets"]
        case "notification":
            current["notificationCount"] = current.get("notificationCount", 0) + 1
        case "notification:dismissed":
            current["notificationCount"] = max(
                0, current.get("notificationCount", 0) - 1
            )
        case _:
            _LOGGER.debug("Unhandled core WebSocket event: %s", event)
            return
    self.async_set_updated_data(current)
```

**Note on `page:changed` payload:** The event sends `activePage` (int) and `page` (single page object) and `widgets`. The coordinator updates `activePage` and `widgets` directly. The `pages` list in coordinator data comes from the REST state and is not replaced by a single-page object — only `activePage` changes via WebSocket.

### 3.5 WebSocket lifecycle

```python
async def async_start_websocket(self) -> None:
    """Create WebSocket client and start the reconnect loop."""

async def async_stop_websocket(self) -> None:
    """Cancel reconnect task and close WebSocket connection."""

async def _ws_reconnect_loop(self) -> None:
    """Connect and listen. On disconnect, retry with exponential backoff."""
    backoff = 1
    while True:
        try:
            await self.ws_client.async_connect()
            backoff = 1  # reset on successful connect
            await self.ws_client.async_listen()
        except HubbleAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return  # do not retry on auth failure
        except HubbleConnectionError:
            pass  # retry after backoff
        except asyncio.CancelledError:
            return
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)
```

---

## 4. `__init__.py` Changes

```python
async def async_setup_entry(hass, entry):
    session = async_get_clientsession(hass)
    client = HubbleApiClient(...)

    # 1. Discovery (required — raises ConfigEntryNotReady on failure)
    try:
        discovery = await client.async_discover()
    except HubbleConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except HubbleAuthError as err:
        raise ConfigEntryAuthFailed from err

    # 2. Create coordinator with discovery data
    coordinator = HubbleCoordinator(hass, entry, client)
    coordinator.discovery = discovery

    # 3. First REST refresh
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # 4. Forward platform setups
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. Start WebSocket (after platforms so handlers can register)
    await coordinator.async_start_websocket()

    return True


async def async_unload_entry(hass, entry):
    coordinator: HubbleCoordinator = entry.runtime_data
    await coordinator.async_stop_websocket()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

---

## 5. Files Changed

| File | Change |
|---|---|
| `api.py` | Add `async_discover()`; remove `async_get_modules()` |
| `websocket.py` | New — `HubbleWebSocketClient` |
| `coordinator.py` | Add `discovery`, `ws_client`, `_module_handlers`; add `is_module_discovered()`, `register_module_handler()`, `_handle_ws_event()`, `async_start_websocket()`, `async_stop_websocket()`, `_ws_reconnect_loop()`; drop modules from gather; SCAN_INTERVAL → 5 min |
| `__init__.py` | Run discovery on setup; start/stop WebSocket; handle `ConfigEntryAuthFailed` from discovery |
| `sensor.py` | `HubbleModuleCountSensor` reads from `coordinator.discovery` |
| `const.py` | `SCAN_INTERVAL = timedelta(minutes=5)` |
| `tests/components/hubble/__init__.py` | Add `MOCK_DISCOVERY` fixture data; remove `"modules"` from `MOCK_STATE` |
| `tests/components/hubble/conftest.py` | Mock `async_discover()` in `setup_integration` |
| `tests/components/hubble/test_websocket.py` | New — WebSocket client unit tests |
| `tests/components/hubble/test_coordinator.py` | New — WebSocket event handling, module routing |
| `tests/components/hubble/test_init.py` | New — discovery on setup, ConfigEntryNotReady on failure, WebSocket start/stop |
| `tests/components/hubble/test_sensor.py` | Update module count test to use discovery data |

---

## 6. Error Handling Summary

| Condition | Behaviour |
|---|---|
| Discovery fails on boot (`HubbleConnectionError`) | `ConfigEntryNotReady` — HA retries setup |
| Discovery fails on boot (`HubbleAuthError`) | `ConfigEntryAuthFailed` — re-auth flow |
| WebSocket auth rejected | `async_start_reauth()` — no reconnect |
| WebSocket connection dropped | Exponential backoff reconnect (1s → 60s cap) |
| REST resync fails | `UpdateFailed` — entities go unavailable |
| Unknown `module:data` event | Logged at DEBUG, dropped |
| Unknown core event | Logged at DEBUG, dropped |

---

## 7. Testing

| File | Coverage |
|---|---|
| `test_websocket.py` | `async_connect` sends auth + subscribe; auth failure raises `HubbleAuthError`; `async_listen` dispatches events to callback; reconnect sends full `subscribe`; `async_add_subscription` sends `add` message and updates internal state |
| `test_coordinator.py` | `page:changed` updates `activePage`; `notification` increments count; `notification:dismissed` decrements (floor 0); `module:data` routes to registered handler; unknown module:data is dropped; `is_module_discovered` returns correct bool |
| `test_init.py` | Discovery called on setup; `ConfigEntryNotReady` on `HubbleConnectionError` from discovery; `async_start_websocket` called after platform setup; `async_stop_websocket` called on unload |
| `test_sensor.py` | Module count reads `coordinator.discovery["modules"]` not `coordinator.data` |
