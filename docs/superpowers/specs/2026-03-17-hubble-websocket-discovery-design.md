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
      {"event": "page:changed", "description": "...", "payload": {...}},
      {"event": "notification", "description": "...", "payload": {...}}
    ]
  },
  "modules": [
    {
      "module": "hubble-timer",
      "version": "1.2.3",
      "description": "...",
      "events": [...],
      "endpoints": [...],
      "instances": [...]
    }
  ]
}
```

**Key field:** module entries use `"module"` (not `"name"`) as the identifier.

Discovery is called once in `async_setup_entry`, before the coordinator is created. If it fails, raise `ConfigEntryNotReady` (connection error) or `ConfigEntryAuthFailed` (auth error). The result is stored as `coordinator.discovery: dict[str, Any]`, initialised to `{}` in `__init__`.

`async_get_modules()` is removed from `api.py` — superseded by the richer discovery response. The `"modules"` key is removed from `coordinator.data`.

### 1.2 Mock discovery data

`tests/components/hubble/__init__.py` adds:

```python
MOCK_DISCOVERY = {
    "core": {
        "events": [
            {"event": "page:changed", "description": "Active page changed.", "payload": {}},
            {"event": "notification", "description": "Notification pushed.", "payload": {}},
            {"event": "notification:dismissed", "description": "Notification dismissed.", "payload": {}},
        ]
    },
    "modules": [
        {
            "module": "hubble-clock",
            "version": "0.2.0",
            "description": "Clock widget.",
            "events": [],
            "endpoints": [],
            "instances": [{"widgetId": 1, "visualization": "digital", "config": {"slug": "clock-1"}}],
        },
        {
            "module": "hubble-weather",
            "version": "1.0.0",
            "description": "Weather widget.",
            "events": [],
            "endpoints": [],
            "instances": [{"widgetId": 2, "visualization": "current", "config": {"slug": "weather-1"}}],
        },
    ],
}
```

### 1.3 Coordinator data

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
| `page:changed` | `activePage` and `widgets` from event payload only — **do not replace `pages` list** |
| `notification` | `notificationCount += 1` |
| `notification:dismissed` | `notificationCount = max(0, notificationCount - 1)` |

The `pages` list is **never updated from WebSocket events** — it only arrives from the REST state endpoint. The `page:changed` payload sends a single page object (`"page"`), not the full list. Replacing `pages` with a single object would break `HubbleCurrentPageSensor`.

The REST resync provides ground-truth correction for any missed WebSocket events.

### 1.4 Module count sensor

`HubbleModuleCountSensor` switches from reading `coordinator.data["modules"]` to `coordinator.discovery.get("modules", [])`. Module entries use `m["module"]` (not `m["name"]`) for the name attribute:

```python
# extra_state_attributes
return {"modules": [m["module"] for m in coordinator.discovery.get("modules", [])]}
```

The module count reflects what was discovered at boot and is static until the entry reloads.

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
        """Receive loop. Returns when connection closes cleanly.
        Raises HubbleConnectionError on error."""

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
     - If WSServerHandshakeError with status 401: raise HubbleAuthError
     - If other aiohttp.ClientError: raise HubbleConnectionError
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
    elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
        break  # clean close — return normally, coordinator reconnects
    elif msg.type == WSMsgType.ERROR:
        raise HubbleConnectionError("WebSocket error")
  # returns normally on clean close
```

### 2.4 Error handling

| Condition | Behaviour |
|---|---|
| `WSServerHandshakeError` with status 401 | Raise `HubbleAuthError` |
| `aiohttp.ClientError` on connect (non-401) | Raise `HubbleConnectionError` |
| `{"error": ...}` auth response | Raise `HubbleAuthError` |
| `WSMsgType.CLOSE` / `WSMsgType.CLOSED` | Return normally (coordinator reconnects) |
| `WSMsgType.ERROR` in receive loop | Raise `HubbleConnectionError` |

---

## 3. Coordinator Changes (`coordinator.py`)

### 3.1 New attributes

```python
discovery: dict[str, Any] = {}     # initialised in __init__; set by async_setup_entry
ws_client: HubbleWebSocketClient | None = None
_module_handlers: dict[tuple[str, str], Callable[[dict], None]]
_ws_reconnect_task: asyncio.Task | None = None
```

`discovery` is initialised to `{}` in `__init__` and assigned the real value by `async_setup_entry` before `async_config_entry_first_refresh()` is called.

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

    # Core events — patch coordinator data in place
    current = dict(self.data) if self.data else {}
    match event:
        case "page:changed":
            # Only update activePage and widgets.
            # Do NOT replace the pages list — the payload sends a single page
            # object ("page"), not the full list. Replacing pages would break
            # HubbleCurrentPageSensor which iterates coordinator.data["pages"].
            current["activePage"] = data.get("activePage", current.get("activePage"))
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

### 3.5 WebSocket lifecycle

```python
async def async_start_websocket(self) -> None:
    """Create WebSocket client and start the reconnect loop."""
    self.ws_client = HubbleWebSocketClient(
        host=..., port=..., api_key=..., session=...,
        on_event=self._handle_ws_event,
    )
    self._ws_reconnect_task = self.hass.async_create_task(
        self._ws_reconnect_loop(), eager_start=False
    )

async def async_stop_websocket(self) -> None:
    """Cancel reconnect task and close WebSocket connection.

    Shutdown sequence:
      1. Cancel the reconnect task (stops the loop).
      2. Await the task so CancelledError is fully propagated.
      3. Call async_disconnect() to close the underlying ws connection.
    """
    if self._ws_reconnect_task is not None:
        self._ws_reconnect_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._ws_reconnect_task
        self._ws_reconnect_task = None
    if self.ws_client is not None:
        await self.ws_client.async_disconnect()
        self.ws_client = None

async def _ws_reconnect_loop(self) -> None:
    """Connect and listen. On disconnect, retry with exponential backoff.

    Clean close (listen returns normally): reconnect after backoff.
    HubbleAuthError: trigger re-auth and exit — do not retry.
    HubbleConnectionError: retry after backoff.
    CancelledError: exit cleanly.
    """
    backoff = 1
    while True:
        try:
            await self.ws_client.async_connect()
            backoff = 1  # reset on successful connect
            await self.ws_client.async_listen()
            # listen returned normally (clean close) — fall through to reconnect
        except HubbleAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return  # do not retry on auth failure
        except HubbleConnectionError:
            pass  # retry after backoff
        except asyncio.CancelledError:
            return  # async_stop_websocket cancelled us
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)
```

---

## 4. `__init__.py` Changes

```python
async def async_setup_entry(hass, entry):
    session = async_get_clientsession(hass)
    client = HubbleApiClient(...)

    # 1. Discovery (required — raises ConfigEntryNotReady / ConfigEntryAuthFailed on failure)
    try:
        discovery = await client.async_discover()
    except HubbleAuthError as err:
        raise ConfigEntryAuthFailed from err
    except HubbleConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # 2. Create coordinator; set discovery before first refresh
    coordinator = HubbleCoordinator(hass, entry, client)
    coordinator.discovery = discovery

    # 3. First REST refresh
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # 4. Forward platform setups (platforms may register module handlers here)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. Start WebSocket (after platforms so handlers are registered before events arrive)
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
| `coordinator.py` | Add `discovery` (default `{}`), `ws_client`, `_module_handlers`; add `is_module_discovered()`, `register_module_handler()`, `_handle_ws_event()`, `async_start_websocket()`, `async_stop_websocket()`, `_ws_reconnect_loop()`; drop modules from gather; `SCAN_INTERVAL` → 5 min |
| `__init__.py` | Run discovery on setup; `ConfigEntryAuthFailed` / `ConfigEntryNotReady` from discovery; start/stop WebSocket |
| `sensor.py` | `HubbleModuleCountSensor` reads from `coordinator.discovery`; use `m["module"]` not `m["name"]` |
| `const.py` | `SCAN_INTERVAL = timedelta(minutes=5)` |
| `tests/components/hubble/__init__.py` | Add `MOCK_DISCOVERY`; remove `"modules"` from `MOCK_STATE`; remove `MOCK_MODULES` |
| `tests/components/hubble/conftest.py` | Mock `async_discover()` returning `MOCK_DISCOVERY` in `setup_integration` |
| `tests/components/hubble/test_websocket.py` | New — WebSocket client unit tests |
| `tests/components/hubble/test_coordinator.py` | New — WebSocket event handling, module routing |
| `tests/components/hubble/test_init.py` | New — discovery on setup, error paths, WebSocket start/stop |
| `tests/components/hubble/test_sensor.py` | Update module count test to read from discovery |

---

## 6. Error Handling Summary

| Condition | Behaviour |
|---|---|
| Discovery fails (`HubbleConnectionError`) | `ConfigEntryNotReady` — HA retries setup |
| Discovery fails (`HubbleAuthError`) | `ConfigEntryAuthFailed` — re-auth flow |
| WS handshake HTTP 401 (`WSServerHandshakeError`) | Raise `HubbleAuthError` in `async_connect` |
| WS auth message rejected (`{"error": ...}`) | Raise `HubbleAuthError` in `async_connect` |
| WS connect other error (`aiohttp.ClientError`) | Raise `HubbleConnectionError` in `async_connect` |
| WS clean close (`WSMsgType.CLOSE/CLOSED`) | `async_listen` returns normally; coordinator reconnects after backoff |
| WS error frame (`WSMsgType.ERROR`) | Raise `HubbleConnectionError`; coordinator reconnects after backoff |
| `HubbleAuthError` in reconnect loop | `async_start_reauth()` called; reconnect loop exits — no further retries |
| `HubbleConnectionError` in reconnect loop | Retry after exponential backoff (1s → 60s cap) |
| REST resync fails (`UpdateFailed`) | Entities go unavailable — WebSocket continues independently |
| Unknown `module:data` event | Logged at DEBUG, dropped |
| Unknown core event | Logged at DEBUG, dropped |

---

## 7. Testing

### `test_websocket.py`
- `async_connect` sends correct auth message then subscribe
- Auth response `{"error": ...}` raises `HubbleAuthError`
- `WSServerHandshakeError` with status 401 raises `HubbleAuthError`
- `async_listen` dispatches TEXT messages to `on_event` callback
- `async_listen` returns normally on `WSMsgType.CLOSE`
- `async_listen` raises `HubbleConnectionError` on `WSMsgType.ERROR`
- `async_add_subscription` sends `{"action": "add", ...}` and updates `_subscriptions`
- Reconnect via `async_connect` sends full `subscribe` (not `add`) built from accumulated `_subscriptions`

### `test_coordinator.py`
- `page:changed` updates `activePage` and `widgets` but does NOT replace `pages` list
- `notification` increments `notificationCount`
- `notification:dismissed` decrements `notificationCount` (floor 0)
- `notification:dismissed` when count is already 0 stays at 0
- `module:data` routes to registered handler with correct `data` dict
- `module:data` with no registered handler is logged and dropped
- `is_module_discovered` returns `True` for present module, `False` for absent
- `register_module_handler` overwrites existing handler for same `(module, topic)`
- `_ws_reconnect_loop` calls `async_start_reauth` and exits on `HubbleAuthError`
- `_ws_reconnect_loop` retries with increasing backoff on `HubbleConnectionError`
- `_ws_reconnect_loop` reconnects after clean close (listen returns normally)
- `async_stop_websocket` cancels task and calls `async_disconnect`

### `test_init.py`
- Discovery called once during `async_setup_entry`
- `ConfigEntryNotReady` raised when discovery raises `HubbleConnectionError`
- `ConfigEntryAuthFailed` raised when discovery raises `HubbleAuthError`
- `async_start_websocket` called after platform setup completes
- `async_stop_websocket` called before platform unload in `async_unload_entry`
- `coordinator.discovery` is set before `async_config_entry_first_refresh`

### `test_sensor.py`
- Module count sensor reads `len(coordinator.discovery["modules"])` not `coordinator.data`
- Module count `extra_state_attributes` uses `m["module"]` field from discovery data
