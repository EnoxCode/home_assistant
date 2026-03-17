# Hubble Timer Integration Design

## Goal

Expose each discovered `hubble-timer` widget instance as a sensor entity in Home Assistant, with real-time state updates via WebSocket and four HA services for control — all using the existing `config_entry_id` + `slug` pattern.

## Background

The Hubble integration already has:
- `coordinator.discovery` — populated at setup from `GET /api/ws/events`; contains a `"modules"` list with each installed module's instances
- `coordinator.register_module_handler(module, topic, handler)` — routes `module:data` WS events to callbacks
- `coordinator.is_module_discovered(module_name)` — checks if a module is installed
- `_pending_module_subs` (to be added) — queues WS module subscriptions before the socket opens
- Notification services in `__init__.py` as the pattern for `config_entry_id`-scoped services

## Architecture

### Files modified

| File | Change |
|---|---|
| `api.py` | Add `async_get_connector_state(module_name)` + `async_timer_start/pause/resume/reset` |
| `coordinator.py` | Add `_pending_module_subs: set[str]` + `add_pending_module_subscription(module)`, update `async_start_websocket` to apply pending subs to ws_client before the reconnect loop starts |
| `sensor.py` | Add `HubbleTimerSensor`; update `async_setup_entry` to create timer sensors + register WS handlers if `hubble-timer` is discovered |
| `__init__.py` | Register 4 new services: `start_timer`, `pause_timer`, `resume_timer`, `reset_timer` |
| `strings.json` / `translations/en.json` | Add `timer` sensor translation key (`"Timer"` as the friendly name, same pattern as `current_page`) |

No new files. Timer sensors live in `sensor.py` alongside the existing sensors.

## Sensor Entity: `HubbleTimerSensor`

One entity per instance in `discovery["modules"]` where `module == "hubble-timer"`, from the `instances` list. Each instance has `config.slug` (e.g. `"test-1"`).

**Unique ID:** `{entry_id}_timer_{slug}`

**`native_value`:** `"idle"` | `"active"` | `"paused"` | `"finished"`

**`extra_state_attributes`:**

| Attribute | Type | Description |
|---|---|---|
| `slug` | str | Timer identifier (always present) |
| `mode` | str \| None | `"countdown"` or `"stopwatch"` |
| `label` | str \| None | Display label from most recent `timer:started` |
| `duration` | float \| None | Total duration in seconds (countdown only) |
| `finishes_at` | str \| None | ISO UTC timestamp when countdown ends; set on start/resume, cleared on pause/finish/reset |
| `elapsed_seconds` | float \| None | Elapsed seconds from `timer:paused` / `timer:resumed` payloads |

### State transitions from WS events

All events carry the timer `slug` in their payload.

| WS topic | New state | Updates |
|---|---|---|
| `timer:started` | `active` | `mode`, `label`, `duration`, `finishes_at` = now + duration (countdown), `elapsed_seconds` = 0 |
| `timer:paused` | `paused` | `elapsed_seconds` from payload, `finishes_at` = None |
| `timer:resumed` | `active` | `elapsed_seconds` from payload, `finishes_at` recomputed = now + (duration - elapsed) |
| `timer:finished` | `finished` | `finishes_at` = None |
| `timer:reset` | `idle` | All attributes cleared |

### Initial state

In `sensor.py` `async_setup_entry`, after creating timer sensors, calls `client.async_get_connector_state("hubble-timer")` which returns the last-emitted payload per topic as a dict `{topic: payload}` (e.g. `{"timer:started": {...}, "timer:paused": {...}}`).

Since the connector-state API returns the last payload **per topic** with no global ordering or timestamps, initial state is determined by applying a fixed priority over the topics present for each slug. Each sensor applies the first matching topic in this order:

1. `timer:paused` → state `paused`, set `elapsed_seconds`
2. `timer:finished` → state `finished`
3. `timer:reset` → state `idle`, clear attributes
4. `timer:started` → state `active`, set `mode`/`label`/`duration`/`finishes_at`
5. `timer:resumed` → state `active`, set `elapsed_seconds`/`finishes_at`

This priority reflects the most useful initial state for common scenarios (a paused or finished timer is more actionable than an ambiguous "active" from a stale start event). Sensors that start with stale state will resync on the next WS event.

If no connector-state data is available for a slug, the sensor defaults to `"idle"`.

### WS dispatch

A `slug → sensor` dict is built at setup time. For each of the 5 topics, one handler is registered via `coordinator.register_module_handler("hubble-timer", topic, handler)`. Each handler looks up the sensor by `data["slug"]` and calls `sensor.handle_event(topic, data)`, which updates state and calls `self.async_write_ha_state()`.

### WS subscription

`sensor.py` calls `coordinator.add_pending_module_subscription("hubble-timer")` during setup. `coordinator.async_start_websocket` applies pending subscriptions to the ws_client (via `async_add_subscription`) before starting the reconnect loop, so the initial subscribe message includes `hubble-timer`.

## API Additions

```python
async def async_get_connector_state(self, module_name: str) -> dict[str, Any]:
    """GET /api/dashboard/connector-state/{module_name}"""

async def async_timer_start(
    self, slug: str, duration: int | None = None, label: str | None = None
) -> dict[str, Any]:
    """POST /api/module/hubble-timer/api/start — duration is int seconds (service schema coerces to int)"""

async def async_timer_pause(self, slug: str) -> dict[str, Any]:
    """POST /api/module/hubble-timer/api/pause"""

async def async_timer_resume(self, slug: str) -> dict[str, Any]:
    """POST /api/module/hubble-timer/api/resume"""

async def async_timer_reset(self, slug: str) -> dict[str, Any]:
    """POST /api/module/hubble-timer/api/reset"""
```

All methods raise `HubbleAuthError` on 401, `HubbleConnectionError` on `aiohttp.ClientError`.

## Services

Registered in `async_setup` in `__init__.py`, following the notification service pattern exactly.

### `hubble.start_timer`
```python
vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector({"integration": "hubble"}),
    vol.Required("slug"): cv.string,
    vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("label"): cv.string,
})
```
Calls `client.async_timer_start(slug, duration, label)`. No coordinator refresh — WS event updates the sensor.

### `hubble.pause_timer` / `hubble.resume_timer` / `hubble.reset_timer`
```python
vol.Schema({
    vol.Required("config_entry_id"): selector.ConfigEntrySelector({"integration": "hubble"}),
    vol.Required("slug"): cv.string,
})
```

All use `_get_coordinator` (already in `__init__.py`). Raise `HomeAssistantError` on `HubbleError`.

## Coordinator Changes

```python
# In __init__:
self._pending_module_subs: set[str] = set()

def add_pending_module_subscription(self, module_name: str) -> None:
    """Queue a module WS subscription to be applied when the socket opens.

    This indirection is needed because platform setup (sensor.py) runs before
    async_start_websocket is called, so ws_client is None at that point.
    async_start_websocket reads _pending_module_subs and applies them to the
    newly-created ws_client before starting the reconnect loop.
    """
    self._pending_module_subs.add(module_name)

# In async_start_websocket, after creating ws_client, before starting task:
# async_add_subscription when _ws is None only updates ws_client._subscriptions
# (no I/O). The updated subscription state is then included in the subscribe
# message sent by async_connect on the first reconnect loop iteration.
if self._pending_module_subs:
    await self.ws_client.async_add_subscription(
        modules=list(self._pending_module_subs)
    )
```

`async_add_subscription` when `_ws` is `None` only updates internal subscription state — no message is sent. The updated state is included in the subscribe message sent on the first `async_connect`.

## Testing

### New tests in `test_sensor.py`
- Timer sensors created when `hubble-timer` is in discovery, not created when absent
- Initial state populated from connector-state response
- State transitions for each WS topic (`timer:started`, `timer:paused`, `timer:resumed`, `timer:finished`, `timer:reset`); use `freezegun` / `time_machine` or `unittest.mock.patch("homeassistant.util.dt.utcnow")` to control `finishes_at` timestamp assertions
- Slug dispatch: events for slug-A do not affect slug-B sensor
- `finishes_at` computed correctly on start and recomputed on resume
- `finishes_at` cleared on pause/finish/reset
- WS subscription added to coordinator pending subs

### New tests in `test_init.py`
- `start_timer` service calls `async_timer_start` with correct args
- `pause_timer` / `resume_timer` / `reset_timer` call correct api methods
- `start_timer` with no duration (stopwatch mode) omits duration arg
- `HubbleError` in service handler raises `HomeAssistantError`

### Updates to `test_api.py`
- `async_get_connector_state` happy path
- `async_timer_start` with and without duration/label
- `async_timer_pause/resume/reset` happy paths
- 401 → `HubbleAuthError`, `ClientError` → `HubbleConnectionError`

### Updates to `conftest.py`
- Mock `async_get_connector_state` returning empty dict by default
- Add `MOCK_TIMER_INSTANCES` to `tests/components/hubble/__init__.py`
- Update `MOCK_DISCOVERY` to include a `hubble-timer` module entry with one instance

## Out of scope

- `start-available` endpoint (starts first idle timer — no slug needed): excluded for now, can be added later as `hubble.start_available_timer`
- Timer stopwatch elapsed tracking (HA doesn't count up — elapsed only updated on pause/resume events from Hubble)
- Multiple `hubble-timer` module entries in discovery (the API only returns one module entry with multiple instances)
