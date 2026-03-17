# Hubble Timer Integration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose each discovered `hubble-timer` widget instance as a sensor entity in HA, with live state from WebSocket events and four services (`start_timer`, `pause_timer`, `resume_timer`, `reset_timer`) that take `config_entry_id` + `slug`.

**Architecture:** Add 5 API methods to `HubbleApiClient`. Extend `HubbleCoordinator` with a pending-subscription queue so `sensor.py` can request the hubble-timer WS subscription before the socket opens. Add `HubbleTimerSensor` in `sensor.py` (one per discovered instance), initialised from connector-state REST API, kept live via `module:data` WS events dispatched by slug.

**Tech Stack:** Python 3.13, Home Assistant `CoordinatorEntity`, `aiohttp`, `homeassistant.util.dt`

---

## Codebase orientation

- `homeassistant/components/hubble/api.py` — `HubbleApiClient`; all HTTP methods raise `HubbleAuthError` on 401 and `HubbleConnectionError` on `aiohttp.ClientError`. Use `_async_post(path, payload)` for POST endpoints that always return JSON; use the `async with self._session.get(...)` pattern directly for GET endpoints (see `async_discover` as the template).
- `homeassistant/components/hubble/coordinator.py` — `HubbleCoordinator`; `register_module_handler(module, topic, handler)` stores one `Callable[[dict], None]` per `(module, topic)` key in `_module_handlers`; `_handle_ws_event` routes `module:data` events to those handlers passing the **inner** `data` payload.
- `homeassistant/components/hubble/sensor.py` — `async_setup_entry` creates sensor entities from `entry.runtime_data` (the coordinator). At call time, `coordinator.discovery` is already set and `coordinator.ws_client` is **None** (WS starts after platform setup).
- `homeassistant/components/hubble/__init__.py` — `async_setup` registers services; uses `_get_coordinator(hass, entry_id)` helper + `_SEND_NOTIFICATION_SCHEMA` as the service pattern to follow exactly.
- `tests/components/hubble/conftest.py` — `setup_integration` fixture; patches `HubbleApiClient`, `async_start_websocket`, `async_stop_websocket` so no real I/O occurs.
- `tests/components/hubble/__init__.py` — shared mock constants.

## Commit convention

Use `--no-verify` for all commits (the `hassfest` pre-commit hook requires `libturbojpeg` which is not in this devcontainer):
```bash
git commit --no-verify -m "..."
```

---

## Task 1: API additions

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Test: `tests/components/hubble/test_api.py`

Add `async_get_connector_state` and four timer action methods to `HubbleApiClient`. No new files.

---

- [ ] **Step 1: Write failing tests for `async_get_connector_state`**

Append to `tests/components/hubble/test_api.py`:

```python
async def test_async_get_connector_state_returns_payload(client) -> None:
    """async_get_connector_state returns parsed JSON from connector-state endpoint."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={"timer:started": {"slug": "timer-1", "mode": "countdown"}}
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_get_connector_state("hubble-timer")

    assert result == {"timer:started": {"slug": "timer-1", "mode": "countdown"}}
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/dashboard/connector-state/hubble-timer",
        headers={"x-api-key": "test-api-key"},
    )


async def test_async_get_connector_state_raises_auth_error_on_401(client) -> None:
    """async_get_connector_state raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_get_connector_state("hubble-timer")


async def test_async_get_connector_state_raises_connection_error(client) -> None:
    """async_get_connector_state raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_get_connector_state("hubble-timer")
```

- [ ] **Step 2: Run and confirm failing**

```bash
pytest tests/components/hubble/test_api.py -k "connector_state" -v
```
Expected: FAIL with `AttributeError: 'HubbleApiClient' object has no attribute 'async_get_connector_state'`

- [ ] **Step 3: Write failing tests for timer action methods**

Append to `tests/components/hubble/test_api.py`:

```python
def _mock_post_response(session, return_value):
    """Helper: make session.post return a 200 JSON response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=return_value)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=mock_response)


async def test_async_timer_start_with_duration_and_label(client) -> None:
    """async_timer_start sends slug, duration, and label to the start endpoint."""
    _mock_post_response(client._session, {"ok": True})

    result = await client.async_timer_start("timer-1", duration=300, label="Pasta")

    assert result == {"ok": True}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/start",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1", "duration": 300, "label": "Pasta"},
    )


async def test_async_timer_start_without_duration_omits_key(client) -> None:
    """async_timer_start without duration sends only slug (stopwatch mode)."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_start("timer-1")

    sent_json = client._session.post.call_args[1]["json"]
    assert sent_json == {"slug": "timer-1"}
    assert "duration" not in sent_json


async def test_async_timer_pause(client) -> None:
    """async_timer_pause POSTs slug to the pause endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_pause("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/pause",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_resume(client) -> None:
    """async_timer_resume POSTs slug to the resume endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_resume("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/resume",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_reset(client) -> None:
    """async_timer_reset POSTs slug to the reset endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_reset("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/reset",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_action_raises_auth_error_on_401(client) -> None:
    """Timer action raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.post = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_timer_pause("timer-1")


async def test_async_timer_action_raises_connection_error(client) -> None:
    """Timer action raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.post = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_timer_reset("timer-1")
```

- [ ] **Step 4: Run and confirm failing**

```bash
pytest tests/components/hubble/test_api.py -k "timer" -v
```
Expected: FAIL with `AttributeError`

- [ ] **Step 5: Implement `async_get_connector_state` in `api.py`**

Add after `async_discover` (around line 88), following the same GET pattern:

```python
async def async_get_connector_state(self, module_name: str) -> dict[str, Any]:
    """Return last-emitted connector state from GET /api/dashboard/connector-state/{module_name}."""
    url = f"{self._base_url}/api/dashboard/connector-state/{module_name}"
    try:
        async with self._session.get(url, headers=self._headers) as response:
            if response.status == 401:
                raise HubbleAuthError("Invalid API key")
            response.raise_for_status()
            return await response.json()
    except HubbleError:
        raise
    except aiohttp.ClientError as err:
        raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err
```

- [ ] **Step 6: Implement timer action methods in `api.py`**

Add at the end of `api.py` (after `async_dismiss_notification`):

```python
async def async_timer_start(
    self,
    slug: str,
    duration: int | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Start or restart a timer — POST /api/module/hubble-timer/api/start."""
    payload: dict[str, Any] = {"slug": slug}
    if duration is not None:
        payload["duration"] = duration
    if label is not None:
        payload["label"] = label
    return await self._async_post("/api/module/hubble-timer/api/start", payload)

async def async_timer_pause(self, slug: str) -> dict[str, Any]:
    """Pause a running timer — POST /api/module/hubble-timer/api/pause."""
    return await self._async_post("/api/module/hubble-timer/api/pause", {"slug": slug})

async def async_timer_resume(self, slug: str) -> dict[str, Any]:
    """Resume a paused timer — POST /api/module/hubble-timer/api/resume."""
    return await self._async_post("/api/module/hubble-timer/api/resume", {"slug": slug})

async def async_timer_reset(self, slug: str) -> dict[str, Any]:
    """Reset a timer to idle — POST /api/module/hubble-timer/api/reset."""
    return await self._async_post("/api/module/hubble-timer/api/reset", {"slug": slug})
```

- [ ] **Step 7: Run all api tests and confirm passing**

```bash
pytest tests/components/hubble/test_api.py -v
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add homeassistant/components/hubble/api.py tests/components/hubble/test_api.py
git commit --no-verify -m "feat(hubble): add connector-state and timer action API methods"
```

---

## Task 2: Coordinator pending-subscription infrastructure

**Files:**
- Modify: `homeassistant/components/hubble/coordinator.py`
- Test: `tests/components/hubble/test_coordinator.py`

Add `_pending_module_subs` set and `add_pending_module_subscription` method to the coordinator. Update `async_start_websocket` to apply pending subs to the ws_client before starting the reconnect loop.

**Why this is needed:** `sensor.py`'s `async_setup_entry` runs during `async_forward_entry_setups`, which is called **before** `async_start_websocket` in `__init__.py`. At that point `coordinator.ws_client` is `None`, so we can't call `ws_client.async_add_subscription` directly. Instead, sensor setup adds the module name to `_pending_module_subs`, and `async_start_websocket` transfers them to the ws_client (which only updates internal subscription state when not yet connected — no I/O).

---

- [ ] **Step 1: Write failing tests**

Append to `tests/components/hubble/test_coordinator.py`:

```python
# ── pending module subscriptions ───────────────────────────────────────────────

async def test_add_pending_module_subscription_queues_module(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """add_pending_module_subscription adds to _pending_module_subs set."""
    coordinator.add_pending_module_subscription("hubble-timer")
    assert "hubble-timer" in coordinator._pending_module_subs


async def test_async_start_websocket_applies_pending_subs(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """async_start_websocket transfers pending module subs to the ws_client."""
    coordinator.add_pending_module_subscription("hubble-timer")

    mock_ws_instance = AsyncMock()

    with patch(
        "homeassistant.components.hubble.coordinator.HubbleWebSocketClient",
        return_value=mock_ws_instance,
    ):
        await coordinator.async_start_websocket()

    mock_ws_instance.async_add_subscription.assert_called_once_with(
        modules=["hubble-timer"]
    )
    # Clean up the background task
    coordinator._ws_reconnect_task.cancel()


async def test_async_start_websocket_skips_sub_call_when_no_pending(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """async_start_websocket does not call async_add_subscription when no pending subs."""
    mock_ws_instance = AsyncMock()

    with patch(
        "homeassistant.components.hubble.coordinator.HubbleWebSocketClient",
        return_value=mock_ws_instance,
    ):
        await coordinator.async_start_websocket()

    mock_ws_instance.async_add_subscription.assert_not_called()
    coordinator._ws_reconnect_task.cancel()
```

- [ ] **Step 2: Run and confirm failing**

```bash
pytest tests/components/hubble/test_coordinator.py -k "pending" -v
```
Expected: FAIL with `AttributeError: 'HubbleCoordinator' object has no attribute 'add_pending_module_subscription'`

- [ ] **Step 3: Add `_pending_module_subs` to `__init__` in `coordinator.py`**

In `HubbleCoordinator.__init__`, after the `_module_handlers` dict (around line 55), add:

```python
        # Pending WS module subscriptions — populated by platform setup before WS opens.
        self._pending_module_subs: set[str] = set()
```

- [ ] **Step 4: Add `add_pending_module_subscription` method in `coordinator.py`**

Add after the `register_module_handler` method (after line 90), before the WebSocket event routing section:

```python
    def add_pending_module_subscription(self, module_name: str) -> None:
        """Queue a module WS subscription to be applied when the socket opens.

        This indirection is needed because platform setup (sensor.py) runs before
        async_start_websocket is called, so ws_client is None at that point.
        async_start_websocket reads _pending_module_subs and transfers them to the
        newly-created ws_client before starting the reconnect loop.
        """
        self._pending_module_subs.add(module_name)
```

- [ ] **Step 5: Update `async_start_websocket` in `coordinator.py`**

Replace the existing `async_start_websocket` method body (keep the docstring and the ws_client creation, add the pending-sub transfer before the task creation):

```python
    async def async_start_websocket(self) -> None:
        """Create WebSocket client and start the reconnect loop."""
        self.ws_client = HubbleWebSocketClient(
            host=self.config_entry.data[CONF_HOST],
            port=self.config_entry.data[CONF_PORT],
            api_key=self.config_entry.data[CONF_API_KEY],
            session=async_get_clientsession(self.hass),
            on_event=self._handle_ws_event,
        )
        # Transfer pending module subscriptions to the ws_client. Since _ws is None
        # at this point, async_add_subscription only updates internal subscription
        # state (no I/O). The updated state is included in the subscribe message
        # sent by async_connect on the first reconnect loop iteration.
        if self._pending_module_subs:
            await self.ws_client.async_add_subscription(
                modules=list(self._pending_module_subs)
            )
        self._ws_reconnect_task = self.hass.async_create_task(
            self._ws_reconnect_loop(),
            eager_start=False,
        )
```

- [ ] **Step 6: Run all coordinator tests and confirm passing**

```bash
pytest tests/components/hubble/test_coordinator.py -v
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add homeassistant/components/hubble/coordinator.py tests/components/hubble/test_coordinator.py
git commit --no-verify -m "feat(hubble): add pending module subscription queue to coordinator"
```

---

## Task 3: Timer sensor

**Files:**
- Modify: `tests/components/hubble/__init__.py` (add timer mock constants)
- Modify: `tests/components/hubble/conftest.py` (mock `async_get_connector_state`)
- Modify: `homeassistant/components/hubble/sensor.py` (add `HubbleTimerSensor`)
- Test: `tests/components/hubble/test_sensor.py`

One `HubbleTimerSensor` per discovered timer instance. Named by slug so entity IDs are predictable (`sensor.kitchen_screen_timer_1`). State live from WS events; initial state from connector-state API on setup.

**Entity naming:** uses `_attr_has_entity_name = True` with `_attr_name = slug`. So slug `"timer-1"` → entity ID `sensor.kitchen_screen_timer_1`.

---

- [ ] **Step 1: Add timer mock constants to `tests/components/hubble/__init__.py`**

Append to the file:

```python
# Timer module instances for hubble-timer tests
MOCK_TIMER_INSTANCES = [
    {"widgetId": 10, "visualization": "countdown", "config": {"slug": "timer-1"}},
    {"widgetId": 11, "visualization": "countdown", "config": {"slug": "timer-2"}},
]

# Discovery payload that includes hubble-timer
MOCK_TIMER_DISCOVERY = {
    **MOCK_DISCOVERY,
    "modules": [
        *MOCK_DISCOVERY["modules"],
        {
            "module": "hubble-timer",
            "version": "1.2.3",
            "description": "Cooking timer.",
            "events": [],
            "endpoints": [],
            "instances": MOCK_TIMER_INSTANCES,
        },
    ],
}
```

- [ ] **Step 2: Update `conftest.py` to mock `async_get_connector_state`**

In `setup_integration`, add a mock for `async_get_connector_state` alongside the existing mocks. Find this block:

```python
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
```

And add immediately after:

```python
        mock_client.async_get_connector_state = AsyncMock(return_value={})
```

- [ ] **Step 3: Write failing tests for timer sensor**

Append to `tests/components/hubble/test_sensor.py`. First add the needed imports at the top of the file:

```python
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from . import MOCK_TIMER_DISCOVERY, MOCK_USER_INPUT
```

Then append the tests:

```python
# ── Timer sensor helpers ───────────────────────────────────────────────────────

@asynccontextmanager
async def _setup_with_timer(hass, connector_state=None):
    """Set up the integration with hubble-timer in discovery."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)
    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_TIMER_DISCOVERY)
        mock_client.async_get_connector_state = AsyncMock(
            return_value=connector_state or {}
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock_client


# ── Timer sensor: creation ─────────────────────────────────────────────────────

async def test_timer_sensors_created_for_each_instance(hass: HomeAssistant) -> None:
    """One timer sensor is created per discovered timer instance."""
    async with _setup_with_timer(hass):
        assert hass.states.get("sensor.kitchen_screen_timer_1") is not None
        assert hass.states.get("sensor.kitchen_screen_timer_2") is not None


async def test_timer_sensors_not_created_when_module_absent(
    hass: HomeAssistant, setup_integration
) -> None:
    """No timer sensors when hubble-timer is not in discovery (standard MOCK_DISCOVERY)."""
    assert hass.states.get("sensor.kitchen_screen_timer_1") is None


async def test_timer_sensor_default_state_is_idle(hass: HomeAssistant) -> None:
    """Timer sensor defaults to 'idle' when no connector-state data exists."""
    async with _setup_with_timer(hass):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "idle"
        assert state.attributes["slug"] == "timer-1"


# ── Timer sensor: initial state from connector-state ──────────────────────────

async def test_timer_sensor_initial_state_paused_from_connector_state(
    hass: HomeAssistant,
) -> None:
    """Timer sensor initialises to paused when connector state has timer:paused."""
    connector_state = {
        "timer:started": {"slug": "timer-1", "mode": "countdown", "duration": 300},
        "timer:paused": {"slug": "timer-1", "elapsed": 120.0},
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "paused"
        assert state.attributes["elapsed_seconds"] == 120.0


async def test_timer_sensor_initial_state_active_from_connector_state(
    hass: HomeAssistant,
) -> None:
    """Timer sensor initialises to active when only timer:started is present."""
    connector_state = {
        "timer:started": {
            "slug": "timer-1",
            "mode": "countdown",
            "duration": 300,
            "label": "Pasta",
        },
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "active"
        assert state.attributes["mode"] == "countdown"
        assert state.attributes["label"] == "Pasta"


async def test_timer_sensor_initial_state_slug_mismatch_defaults_idle(
    hass: HomeAssistant,
) -> None:
    """Connector-state payload for a different slug does not initialise this sensor."""
    connector_state = {
        "timer:paused": {"slug": "timer-2", "elapsed": 60.0},
    }
    async with _setup_with_timer(hass, connector_state=connector_state):
        # timer-1 has no matching connector-state → stays idle
        state = hass.states.get("sensor.kitchen_screen_timer_1")
        assert state.state == "idle"


# ── Timer sensor: WS event state transitions ──────────────────────────────────

async def test_timer_started_event_sets_active_state(hass: HomeAssistant) -> None:
    """timer:started WS event sets state to active with finishes_at."""
    fake_now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)

    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        with patch(
            "homeassistant.components.hubble.sensor.dt_util.utcnow",
            return_value=fake_now,
        ):
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:started",
                    "data": {
                        "slug": "timer-1",
                        "mode": "countdown",
                        "duration": 300,
                        "label": "Pasta",
                    },
                },
            )
            await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "active"
    assert state.attributes["mode"] == "countdown"
    assert state.attributes["label"] == "Pasta"
    assert state.attributes["duration"] == 300
    expected = (fake_now + timedelta(seconds=300)).isoformat()
    assert state.attributes["finishes_at"] == expected


async def test_timer_paused_event_sets_paused_state(hass: HomeAssistant) -> None:
    """timer:paused WS event sets state to paused, stores elapsed, clears finishes_at."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:paused",
                "data": {"slug": "timer-1", "elapsed": 42.0},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "paused"
    assert state.attributes["elapsed_seconds"] == 42.0
    assert "finishes_at" not in state.attributes


async def test_timer_resumed_recomputes_finishes_at(hass: HomeAssistant) -> None:
    """timer:resumed recomputes finishes_at from remaining = duration - elapsed."""
    fake_now = datetime(2026, 3, 17, 12, 0, 0, tzinfo=timezone.utc)
    # Start first so duration is known
    connector_state = {
        "timer:paused": {"slug": "timer-1", "elapsed": 60.0},
        "timer:started": {"slug": "timer-1", "mode": "countdown", "duration": 300},
    }

    async with _setup_with_timer(hass, connector_state=connector_state) as (entry, _):
        coordinator = entry.runtime_data
        with patch(
            "homeassistant.components.hubble.sensor.dt_util.utcnow",
            return_value=fake_now,
        ):
            coordinator._handle_ws_event(
                "module:data",
                {
                    "module": "hubble-timer",
                    "topic": "timer:resumed",
                    "data": {"slug": "timer-1", "elapsed": 60.0},
                },
            )
            await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "active"
    # remaining = 300 - 60 = 240
    expected = (fake_now + timedelta(seconds=240)).isoformat()
    assert state.attributes["finishes_at"] == expected


async def test_timer_finished_event(hass: HomeAssistant) -> None:
    """timer:finished WS event sets state to finished, clears finishes_at."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:finished",
                "data": {"slug": "timer-1", "label": "Done", "duration": 300},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "finished"
    assert "finishes_at" not in state.attributes


async def test_timer_reset_event_clears_state(hass: HomeAssistant) -> None:
    """timer:reset WS event returns sensor to idle, clears all attributes."""
    connector_state = {
        "timer:started": {"slug": "timer-1", "mode": "countdown", "duration": 300, "label": "Test"},
    }
    async with _setup_with_timer(hass, connector_state=connector_state) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:reset",
                "data": {"slug": "timer-1"},
            },
        )
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_timer_1")
    assert state.state == "idle"
    assert "label" not in state.attributes
    assert "mode" not in state.attributes
    assert "duration" not in state.attributes
    assert "finishes_at" not in state.attributes
    assert "elapsed_seconds" not in state.attributes


# ── Timer sensor: slug dispatch ────────────────────────────────────────────────

async def test_ws_event_for_one_slug_does_not_affect_other(
    hass: HomeAssistant,
) -> None:
    """WS event for timer-1 slug does not change timer-2 sensor state."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        coordinator._handle_ws_event(
            "module:data",
            {
                "module": "hubble-timer",
                "topic": "timer:paused",
                "data": {"slug": "timer-1", "elapsed": 10.0},
            },
        )
        await hass.async_block_till_done()

    assert hass.states.get("sensor.kitchen_screen_timer_1").state == "paused"
    assert hass.states.get("sensor.kitchen_screen_timer_2").state == "idle"


async def test_pending_module_sub_registered_when_timer_discovered(
    hass: HomeAssistant,
) -> None:
    """add_pending_module_subscription is called for hubble-timer when discovered."""
    async with _setup_with_timer(hass) as (entry, _):
        coordinator = entry.runtime_data
        assert "hubble-timer" in coordinator._pending_module_subs
```

- [ ] **Step 4: Run and confirm failing**

```bash
pytest tests/components/hubble/test_sensor.py -k "timer" -v
```
Expected: FAIL with `AttributeError` or import errors

- [ ] **Step 5: Add `HubbleTimerSensor` to `sensor.py`**

At the top of `sensor.py`, add missing imports. The full updated import block should be:

```python
"""Hubble sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import timedelta

from homeassistant.util import dt as dt_util

from .api import HubbleAuthError, HubbleConnectionError
from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator
```

- [ ] **Step 6: Add timer constants at module level in `sensor.py`**

Add after the imports, before `async_setup_entry`:

```python
_TIMER_MODULE = "hubble-timer"
_TIMER_TOPICS: tuple[str, ...] = (
    "timer:started",
    "timer:paused",
    "timer:resumed",
    "timer:finished",
    "timer:reset",
)
# Priority order for initialising sensor state from connector-state data.
# Higher priority = checked first. The order reflects "most definitive current
# state": paused > finished > reset > started > resumed.
_INIT_PRIORITY: tuple[str, ...] = (
    "timer:paused",
    "timer:finished",
    "timer:reset",
    "timer:started",
    "timer:resumed",
)
```

- [ ] **Step 7: Update `async_setup_entry` in `sensor.py`**

Replace the existing `async_setup_entry` function entirely:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble sensors from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        HubbleCurrentPageSensor(coordinator, entry),
        HubbleModuleCountSensor(coordinator, entry),
        HubbleNotificationCountSensor(coordinator, entry),
    ]

    if coordinator.is_module_discovered(_TIMER_MODULE):
        timer_module = next(
            m
            for m in coordinator.discovery.get("modules", [])
            if m["module"] == _TIMER_MODULE
        )
        timer_sensors: dict[str, HubbleTimerSensor] = {
            inst["config"]["slug"]: HubbleTimerSensor(
                coordinator, entry, inst["config"]["slug"]
            )
            for inst in timer_module.get("instances", [])
        }
        entities.extend(timer_sensors.values())

        # Fetch connector state for best-effort initial sensor values.
        try:
            connector_state = await coordinator.client.async_get_connector_state(
                _TIMER_MODULE
            )
        except (HubbleAuthError, HubbleConnectionError):
            connector_state = {}

        # Initialise each sensor from the highest-priority topic whose payload
        # matches the sensor's slug.
        for sensor in timer_sensors.values():
            for topic in _INIT_PRIORITY:
                payload = connector_state.get(topic)
                if payload and payload.get("slug") == sensor.slug:
                    sensor.apply_topic(topic, payload)
                    break

        # Register one WS handler per topic; each dispatches to the right sensor
        # by slug from the closure over timer_sensors.
        for topic in _TIMER_TOPICS:
            def _make_handler(t: str) -> Callable[[dict[str, Any]], None]:
                def _handler(data: dict[str, Any]) -> None:
                    s = timer_sensors.get(data.get("slug", ""))
                    if s:
                        s.handle_event(t, data)
                return _handler
            coordinator.register_module_handler(_TIMER_MODULE, topic, _make_handler(topic))

        coordinator.add_pending_module_subscription(_TIMER_MODULE)

    async_add_entities(entities)
```

- [ ] **Step 8: Add `HubbleTimerSensor` class to `sensor.py`**

Append at the end of `sensor.py`:

```python
class HubbleTimerSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor representing one Hubble timer widget instance.

    State: idle | active | paused | finished.
    Updated live from module:data WS events; initialised from connector-state API.
    Named by slug so the entity ID is sensor.{device}_{slug} (hyphens → underscores).
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
        slug: str,
    ) -> None:
        """Initialise the timer sensor."""
        super().__init__(coordinator)
        self._slug = slug
        self._attr_name = slug  # e.g. "timer-1" → sensor.kitchen_screen_timer_1
        self._attr_unique_id = f"{entry.entry_id}_timer_{slug}"
        self._attr_device_info = _device_info(entry)
        # Internal timer state — written by apply_topic / handle_event.
        self._state: str = "idle"
        self._mode: str | None = None
        self._label: str | None = None
        self._duration: float | None = None
        self._finishes_at: str | None = None
        self._elapsed_seconds: float | None = None

    @property
    def slug(self) -> str:
        """Return the timer slug."""
        return self._slug

    @property
    def native_value(self) -> str:
        """Return the timer state."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return timer attributes."""
        attrs: dict[str, Any] = {"slug": self._slug}
        if self._mode is not None:
            attrs["mode"] = self._mode
        if self._label is not None:
            attrs["label"] = self._label
        if self._duration is not None:
            attrs["duration"] = self._duration
        if self._finishes_at is not None:
            attrs["finishes_at"] = self._finishes_at
        if self._elapsed_seconds is not None:
            attrs["elapsed_seconds"] = self._elapsed_seconds
        return attrs

    def handle_event(self, topic: str, data: dict[str, Any]) -> None:
        """Apply a WS timer event and push the new state to HA."""
        self.apply_topic(topic, data)
        self.async_write_ha_state()

    def apply_topic(self, topic: str, data: dict[str, Any]) -> None:
        """Apply a topic payload to internal state (no HA state write).

        Called both from handle_event (WS) and from async_setup_entry
        (connector-state initialisation).
        """
        match topic:
            case "timer:started":
                self._state = "active"
                self._mode = data.get("mode")
                self._label = data.get("label")
                self._duration = data.get("duration")
                self._elapsed_seconds = 0.0
                if self._duration is not None:
                    self._finishes_at = (
                        dt_util.utcnow() + timedelta(seconds=self._duration)
                    ).isoformat()
                else:
                    self._finishes_at = None
            case "timer:paused":
                self._state = "paused"
                self._elapsed_seconds = data.get("elapsed")
                self._finishes_at = None
            case "timer:resumed":
                self._state = "active"
                self._elapsed_seconds = data.get("elapsed")
                if self._duration is not None and self._elapsed_seconds is not None:
                    remaining = self._duration - self._elapsed_seconds
                    self._finishes_at = (
                        dt_util.utcnow() + timedelta(seconds=remaining)
                    ).isoformat()
            case "timer:finished":
                self._state = "finished"
                self._finishes_at = None
            case "timer:reset":
                self._state = "idle"
                self._mode = None
                self._label = None
                self._duration = None
                self._finishes_at = None
                self._elapsed_seconds = None
```

- [ ] **Step 9: Run all sensor tests and confirm passing**

```bash
pytest tests/components/hubble/test_sensor.py -v
```
Expected: all pass

- [ ] **Step 10: Run the full hubble test suite**

```bash
pytest tests/components/hubble/ -v
```
Expected: all pass

- [ ] **Step 11: Lint**

```bash
ruff check homeassistant/components/hubble/sensor.py --fix
ruff format homeassistant/components/hubble/sensor.py
```

- [ ] **Step 12: Commit**

```bash
git add \
  homeassistant/components/hubble/sensor.py \
  tests/components/hubble/__init__.py \
  tests/components/hubble/conftest.py \
  tests/components/hubble/test_sensor.py
git commit --no-verify -m "feat(hubble): add HubbleTimerSensor with WS updates and connector-state init"
```

---

## Task 4: Timer services and strings

**Files:**
- Modify: `homeassistant/components/hubble/__init__.py`
- Modify: `homeassistant/components/hubble/strings.json`
- Test: `tests/components/hubble/test_init.py`

Register four services (`start_timer`, `pause_timer`, `resume_timer`, `reset_timer`) following the exact pattern of the existing notification services. No coordinator refresh — the WS event will update the sensor state.

---

- [ ] **Step 1: Write failing tests**

Append to `tests/components/hubble/test_init.py`. First add the needed import at the top:

```python
from unittest.mock import call
```

Then append:

```python
# ── Timer services ─────────────────────────────────────────────────────────────

async def test_start_timer_service_calls_api(hass: HomeAssistant) -> None:
    """start_timer service calls async_timer_start with slug, duration, label."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_start = AsyncMock(return_value={"ok": True})
        await hass.services.async_call(
            "hubble",
            "start_timer",
            {
                "config_entry_id": entry.entry_id,
                "slug": "timer-1",
                "duration": 300,
                "label": "Pasta",
            },
            blocking=True,
        )

    mock_client.async_timer_start.assert_called_once_with(
        slug="timer-1", duration=300, label="Pasta"
    )


async def test_start_timer_service_stopwatch_mode(hass: HomeAssistant) -> None:
    """start_timer service without duration passes duration=None (stopwatch)."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_start = AsyncMock(return_value={"ok": True})
        await hass.services.async_call(
            "hubble",
            "start_timer",
            {"config_entry_id": entry.entry_id, "slug": "timer-1"},
            blocking=True,
        )

    mock_client.async_timer_start.assert_called_once_with(
        slug="timer-1", duration=None, label=None
    )


async def test_pause_timer_service_calls_api(hass: HomeAssistant) -> None:
    """pause_timer service calls async_timer_pause with slug."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_pause = AsyncMock(return_value={"ok": True})
        await hass.services.async_call(
            "hubble",
            "pause_timer",
            {"config_entry_id": entry.entry_id, "slug": "timer-1"},
            blocking=True,
        )

    mock_client.async_timer_pause.assert_called_once_with("timer-1")


async def test_resume_timer_service_calls_api(hass: HomeAssistant) -> None:
    """resume_timer service calls async_timer_resume with slug."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_resume = AsyncMock(return_value={"ok": True})
        await hass.services.async_call(
            "hubble",
            "resume_timer",
            {"config_entry_id": entry.entry_id, "slug": "timer-1"},
            blocking=True,
        )

    mock_client.async_timer_resume.assert_called_once_with("timer-1")


async def test_reset_timer_service_calls_api(hass: HomeAssistant) -> None:
    """reset_timer service calls async_timer_reset with slug."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_reset = AsyncMock(return_value={"ok": True})
        await hass.services.async_call(
            "hubble",
            "reset_timer",
            {"config_entry_id": entry.entry_id, "slug": "timer-1"},
            blocking=True,
        )

    mock_client.async_timer_reset.assert_called_once_with("timer-1")


async def test_timer_service_raises_ha_error_on_hubble_error(
    hass: HomeAssistant,
) -> None:
    """Timer service raises HomeAssistantError when HubbleError is raised."""
    from homeassistant.exceptions import HomeAssistantError

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_timer_pause = AsyncMock(
            side_effect=HubbleConnectionError("offline")
        )
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "hubble",
                "pause_timer",
                {"config_entry_id": entry.entry_id, "slug": "timer-1"},
                blocking=True,
            )
```

Add the following imports to `test_init.py`. `HubbleAuthError` is already imported; add these two lines unconditionally at the top with the other imports:

```python
import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
```

- [ ] **Step 2: Run and confirm failing**

```bash
pytest tests/components/hubble/test_init.py -k "timer" -v
```
Expected: FAIL with `ServiceNotFound` or similar

- [ ] **Step 3: Add service schemas to `__init__.py`**

After `_DISMISS_NOTIFICATION_SCHEMA` (around line 55), add:

```python
_START_TIMER_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("slug"): cv.string,
        vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        vol.Optional("label"): cv.string,
    }
)

_TIMER_SLUG_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("slug"): cv.string,
    }
)
```

- [ ] **Step 4: Add service handlers in `async_setup` in `__init__.py`**

Inside `async_setup`, after the existing `handle_dismiss_notification` function, add:

```python
    async def handle_start_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_timer_start(
                slug=call.data["slug"],
                duration=call.data.get("duration"),
                label=call.data.get("label"),
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_pause_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_timer_pause(call.data["slug"])
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_resume_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_timer_resume(call.data["slug"])
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_reset_timer(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_timer_reset(call.data["slug"])
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
```

- [ ] **Step 5: Register services in `async_setup` in `__init__.py`**

After the existing `hass.services.async_register` calls for notification services, add:

```python
    hass.services.async_register(
        "hubble", "start_timer", handle_start_timer, schema=_START_TIMER_SCHEMA
    )
    hass.services.async_register(
        "hubble", "pause_timer", handle_pause_timer, schema=_TIMER_SLUG_SCHEMA
    )
    hass.services.async_register(
        "hubble", "resume_timer", handle_resume_timer, schema=_TIMER_SLUG_SCHEMA
    )
    hass.services.async_register(
        "hubble", "reset_timer", handle_reset_timer, schema=_TIMER_SLUG_SCHEMA
    )
```

- [ ] **Step 6: Update `strings.json`**

In the `"services"` object, add four new entries after `"dismiss_notification"`:

```json
    "start_timer": {
      "name": "Start timer",
      "description": "Starts or restarts a Hubble timer widget.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard."
        },
        "slug": {
          "name": "Slug",
          "description": "Timer widget slug (e.g. timer-1)."
        },
        "duration": {
          "name": "Duration",
          "description": "Duration in seconds. Omit for stopwatch mode."
        },
        "label": {
          "name": "Label",
          "description": "Display label for this timer run."
        }
      }
    },
    "pause_timer": {
      "name": "Pause timer",
      "description": "Pauses a running Hubble timer.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard."
        },
        "slug": {
          "name": "Slug",
          "description": "Timer widget slug."
        }
      }
    },
    "resume_timer": {
      "name": "Resume timer",
      "description": "Resumes a paused Hubble timer.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard."
        },
        "slug": {
          "name": "Slug",
          "description": "Timer widget slug."
        }
      }
    },
    "reset_timer": {
      "name": "Reset timer",
      "description": "Resets a Hubble timer to idle.",
      "fields": {
        "config_entry_id": {
          "name": "Hubble instance",
          "description": "The Hubble dashboard."
        },
        "slug": {
          "name": "Slug",
          "description": "Timer widget slug."
        }
      }
    }
```

- [ ] **Step 7: Run all init tests and confirm passing**

```bash
pytest tests/components/hubble/test_init.py -v
```
Expected: all pass

- [ ] **Step 8: Run the full test suite**

```bash
pytest tests/components/hubble/ -v
```
Expected: all pass

- [ ] **Step 9: Lint**

```bash
ruff check homeassistant/components/hubble/__init__.py --fix
ruff format homeassistant/components/hubble/__init__.py
```

- [ ] **Step 10: Commit**

```bash
git add \
  homeassistant/components/hubble/__init__.py \
  homeassistant/components/hubble/strings.json \
  tests/components/hubble/test_init.py
git commit --no-verify -m "feat(hubble): add start_timer, pause_timer, resume_timer, reset_timer services"
```
