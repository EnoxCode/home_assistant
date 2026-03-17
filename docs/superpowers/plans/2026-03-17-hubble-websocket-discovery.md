# Hubble WebSocket & Discovery Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 30s REST poll with WebSocket push for `page:changed` and notification events, add a discovery call on boot, and build the module entity infrastructure.

**Architecture:** A new `HubbleWebSocketClient` in `websocket.py` owns the connection lifecycle. The coordinator stores `discovery` data from `GET /api/ws/events`, routes WebSocket events via `_handle_ws_event`, and manages the reconnect loop. A 5-minute REST resync runs as fallback. Core entities always exist; module entities are conditional on discovery.

**Tech Stack:** Home Assistant core, `aiohttp` WebSocket, `asyncio`, `voluptuous`, Python 3.13+

---

## File Map

**Created:**
- `homeassistant/components/hubble/websocket.py` — `HubbleWebSocketClient`
- `tests/components/hubble/test_websocket.py`
- `tests/components/hubble/test_coordinator.py`
- `tests/components/hubble/test_init.py`

**Modified:**
- `homeassistant/components/hubble/api.py` — add `async_discover()`; remove `async_get_modules()`
- `homeassistant/components/hubble/coordinator.py` — add `discovery`, `ws_client`, `_module_handlers`; remove modules from gather; add module infrastructure + event routing + WebSocket lifecycle; `SCAN_INTERVAL` → 5 min
- `homeassistant/components/hubble/__init__.py` — discovery call on setup; start/stop WebSocket
- `homeassistant/components/hubble/sensor.py` — `HubbleModuleCountSensor` reads from `coordinator.discovery`
- `homeassistant/components/hubble/const.py` — `SCAN_INTERVAL = timedelta(minutes=5)`
- `tests/components/hubble/__init__.py` — add `MOCK_DISCOVERY`; remove `MOCK_MODULES`; remove `"modules"` from `MOCK_STATE`
- `tests/components/hubble/conftest.py` — mock `async_discover`; remove `async_get_modules` mock; patch `async_start_websocket` + `async_stop_websocket`
- `tests/components/hubble/test_sensor.py` — update module count test; remove `MOCK_MODULES` import
- `tests/components/hubble/test_services.py` — replace `async_get_modules` with `async_discover` in manual patches

---

## Task 1: Discovery API method

**Files:**
- Modify: `homeassistant/components/hubble/api.py`

- [ ] **Step 1: Write the failing test**

Add a new test file `tests/components/hubble/test_api.py`:

```python
"""Tests for HubbleApiClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.components.hubble.api import (
    HubbleApiClient,
    HubbleAuthError,
    HubbleConnectionError,
)

from . import MOCK_DISCOVERY


@pytest.fixture
def client():
    """Return a HubbleApiClient with a mock session."""
    session = MagicMock()
    return HubbleApiClient(
        host="kitchen-screen",
        port=3000,
        api_key="test-api-key",
        session=session,
    )


async def test_async_discover_returns_payload(client) -> None:
    """async_discover returns the parsed JSON from GET /api/ws/events."""
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=MOCK_DISCOVERY)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_discover()

    assert result == MOCK_DISCOVERY
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/ws/events",
        headers={"x-api-key": "test-api-key"},
    )


async def test_async_discover_raises_auth_error_on_401(client) -> None:
    """async_discover raises HubbleAuthError on HTTP 401."""
    mock_response = AsyncMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_discover()


async def test_async_discover_raises_connection_error(client) -> None:
    """async_discover raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_discover()
```

- [ ] **Step 2: Add `MOCK_DISCOVERY` to test fixtures (needed for the test above)**

Replace `tests/components/hubble/__init__.py`:

```python
"""Tests for the Hubble integration."""

MOCK_USER_INPUT = {
    "name": "Kitchen Screen",
    "host": "kitchen-screen",
    "port": 3000,
    "api_key": "test-api-key",
}

# Raw response from GET /api/dashboard/state (before coordinator merges)
MOCK_DASHBOARD_STATE = {
    "activePage": 1,
    "screenOn": True,
    "pages": [
        {"id": 1, "slug": "home", "name": "Home"},
        {"id": 2, "slug": "media", "name": "Media"},
    ],
    "widgets": [],
    "templateId": "standard",
    "selectedWidgetId": None,
}

MOCK_NOTIFY_COUNT = 2

# Merged coordinator.data (what _async_update_data returns — no "modules" key)
MOCK_STATE = {
    **MOCK_DASHBOARD_STATE,
    "notificationCount": MOCK_NOTIFY_COUNT,
}

# Discovery payload from GET /api/ws/events
MOCK_DISCOVERY = {
    "core": {
        "events": [
            {"event": "page:changed", "description": "Active page changed.", "payload": {}},
            {"event": "notification", "description": "Notification pushed.", "payload": {}},
            {
                "event": "notification:dismissed",
                "description": "Notification dismissed.",
                "payload": {},
            },
        ]
    },
    "modules": [
        {
            "module": "hubble-clock",
            "version": "0.2.0",
            "description": "Clock widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {"widgetId": 1, "visualization": "digital", "config": {"slug": "clock-1"}}
            ],
        },
        {
            "module": "hubble-weather",
            "version": "1.0.0",
            "description": "Weather widget.",
            "events": [],
            "endpoints": [],
            "instances": [
                {"widgetId": 2, "visualization": "current", "config": {"slug": "weather-1"}}
            ],
        },
    ],
}
```

- [ ] **Step 3: Run tests — expect failure** (`async_discover` not yet implemented)

```bash
pytest tests/components/hubble/test_api.py -v
```

Expected: FAIL — `HubbleApiClient` has no `async_discover` attribute.

- [ ] **Step 4: Add `async_discover` to `api.py`**

Append after `async_get_notify_count` in `homeassistant/components/hubble/api.py`:

```python
    async def async_discover(self) -> dict[str, Any]:
        """Return the discovery payload from GET /api/ws/events."""
        url = f"{self._base_url}/api/ws/events"
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

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/components/hubble/test_api.py -v
```

Expected: All 3 pass.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        tests/components/hubble/__init__.py \
        tests/components/hubble/test_api.py
git commit --no-verify -m "feat(hubble): add async_discover API method and MOCK_DISCOVERY fixture"
```

---

## Task 2: WebSocket client

**Files:**
- Create: `homeassistant/components/hubble/websocket.py`
- Create: `tests/components/hubble/test_websocket.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/components/hubble/test_websocket.py`:

```python
"""Tests for HubbleWebSocketClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.websocket import HubbleWebSocketClient


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ws_message(msg_type: aiohttp.WSMsgType, data=None) -> aiohttp.WSMessage:
    """Build an aiohttp WSMessage."""
    return aiohttp.WSMessage(type=msg_type, data=data, extra=None)


def _make_ws(messages: list[aiohttp.WSMessage]) -> MagicMock:
    """Return a mock ClientWebSocketResponse that yields messages."""

    async def _aiter():
        for msg in messages:
            yield msg

    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()
    ws.__aiter__ = MagicMock(return_value=_aiter())
    return ws


def _make_client(ws_mock=None, on_event=None):
    """Return a HubbleWebSocketClient with a mock session."""
    session = MagicMock()
    if ws_mock is not None:
        session.ws_connect = AsyncMock(return_value=ws_mock)
    client = HubbleWebSocketClient(
        host="kitchen-screen",
        port=3000,
        api_key="test-api-key",
        session=session,
        on_event=on_event or (lambda event, data: None),
    )
    return client, session


# ── async_connect ──────────────────────────────────────────────────────────────

async def test_connect_sends_auth_and_subscribe() -> None:
    """async_connect sends auth message then subscribe message."""
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()

    # Simulate auth success response
    auth_response = aiohttp.WSMessage(
        type=aiohttp.WSMsgType.TEXT,
        data=json.dumps({"authenticated": True, "clientType": "external"}),
        extra=None,
    )
    ws.receive = AsyncMock(return_value=auth_response)

    client, session = _make_client(ws_mock=ws)
    await client.async_connect()

    # First send: auth
    first_call = json.loads(ws.send_str.call_args_list[0][0][0])
    assert first_call == {"action": "auth", "apiKey": "test-api-key"}

    # Second send: subscribe with core events
    second_call = json.loads(ws.send_str.call_args_list[1][0][0])
    assert second_call["action"] == "subscribe"
    assert set(second_call["events"]) == {
        "page:changed",
        "notification",
        "notification:dismissed",
    }


async def test_connect_raises_auth_error_on_error_response() -> None:
    """async_connect raises HubbleAuthError when server returns {"error": ...}."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"error": "Invalid API key"}),
            extra=None,
        )
    )

    client, session = _make_client(ws_mock=ws)

    with pytest.raises(HubbleAuthError):
        await client.async_connect()


async def test_connect_raises_auth_error_on_401_handshake() -> None:
    """async_connect raises HubbleAuthError on HTTP 401 WS handshake."""
    client, session = _make_client()
    session.ws_connect = AsyncMock(
        side_effect=aiohttp.WSServerHandshakeError(
            request_info=MagicMock(), history=(), status=401
        )
    )

    with pytest.raises(HubbleAuthError):
        await client.async_connect()


async def test_connect_raises_connection_error_on_client_error() -> None:
    """async_connect raises HubbleConnectionError on aiohttp.ClientError."""
    client, session = _make_client()
    session.ws_connect = AsyncMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_connect()


# ── async_listen ───────────────────────────────────────────────────────────────

async def test_listen_dispatches_text_messages() -> None:
    """async_listen calls on_event for each TEXT message."""
    received = []

    ws = _make_ws([
        _ws_message(
            aiohttp.WSMsgType.TEXT,
            json.dumps({"event": "page:changed", "data": {"activePage": 2}}),
        ),
        _ws_message(
            aiohttp.WSMsgType.TEXT,
            json.dumps({"event": "notification", "data": {"id": "abc"}}),
        ),
        _ws_message(aiohttp.WSMsgType.CLOSED),
    ])

    client, _ = _make_client(ws_mock=ws, on_event=lambda e, d: received.append((e, d)))

    # Manually set the ws so we can call async_listen directly
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )
    await client.async_connect()
    await client.async_listen()

    assert ("page:changed", {"activePage": 2}) in received
    assert ("notification", {"id": "abc"}) in received


async def test_listen_returns_on_clean_close() -> None:
    """async_listen returns normally on WSMsgType.CLOSE."""
    ws = _make_ws([_ws_message(aiohttp.WSMsgType.CLOSE)])
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()
    # Should return without raising
    await client.async_listen()


async def test_listen_raises_on_ws_error() -> None:
    """async_listen raises HubbleConnectionError on WSMsgType.ERROR."""
    ws = _make_ws([_ws_message(aiohttp.WSMsgType.ERROR)])
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()

    with pytest.raises(HubbleConnectionError):
        await client.async_listen()


# ── async_add_subscription ─────────────────────────────────────────────────────

async def test_add_subscription_sends_add_message() -> None:
    """async_add_subscription sends {"action": "add", ...} to the live connection."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()
    ws.send_str.reset_mock()  # clear auth + subscribe calls

    await client.async_add_subscription(modules=["hubble-timer"])

    sent = json.loads(ws.send_str.call_args[0][0])
    assert sent["action"] == "add"
    assert "hubble-timer" in sent["modules"]


async def test_add_subscription_updates_internal_state() -> None:
    """async_add_subscription updates _subscriptions so reconnect replays it."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, session = _make_client(ws_mock=ws)
    await client.async_connect()
    await client.async_add_subscription(modules=["hubble-timer"])

    assert "hubble-timer" in client._subscriptions["modules"]

    # Simulate reconnect: a new ws_connect call should send full subscribe
    ws2 = MagicMock()
    ws2.send_str = AsyncMock()
    ws2.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )
    session.ws_connect = AsyncMock(return_value=ws2)
    await client.async_connect()

    # The subscribe message on reconnect must include hubble-timer
    subscribe_call = next(
        json.loads(call[0][0])
        for call in ws2.send_str.call_args_list
        if json.loads(call[0][0]).get("action") == "subscribe"
    )
    assert "hubble-timer" in subscribe_call.get("modules", [])
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/components/hubble/test_websocket.py -v
```

Expected: FAIL — `homeassistant.components.hubble.websocket` module not found.

- [ ] **Step 3: Create `websocket.py`**

Create `homeassistant/components/hubble/websocket.py`:

```python
"""Hubble WebSocket client."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from aiohttp import WSMsgType

from .api import HubbleAuthError, HubbleConnectionError

_LOGGER = logging.getLogger(__name__)

# Core events subscribed to by default on every connection.
_DEFAULT_EVENTS: frozenset[str] = frozenset(
    {"page:changed", "notification", "notification:dismissed"}
)


class HubbleWebSocketClient:
    """Manage the Hubble WebSocket connection lifecycle.

    Does not retry — the coordinator controls reconnection timing.
    """

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
        on_event: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Initialise the client."""
        self._url = f"ws://{host}:{port}/ws"
        self._api_key = api_key
        self._session = session
        self._on_event = on_event
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        # Accumulated subscription state — replayed as a full subscribe on reconnect.
        self._subscriptions: dict[str, set[str]] = {
            "events": set(_DEFAULT_EVENTS),
            "modules": set(),
            "moduleTopics": set(),
        }

    # ── Public interface ────────────────────────────────────────────────────────

    async def async_connect(self) -> None:
        """Open connection, authenticate, and send initial subscribe."""
        try:
            self._ws = await self._session.ws_connect(self._url)
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise HubbleAuthError(
                    "WebSocket handshake rejected: invalid API key"
                ) from err
            raise HubbleConnectionError(
                f"WebSocket handshake failed: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(
                f"Cannot connect to Hubble WebSocket: {err}"
            ) from err

        # Authenticate
        await self._ws.send_str(
            json.dumps({"action": "auth", "apiKey": self._api_key})
        )
        msg = await self._ws.receive()
        if msg.type != WSMsgType.TEXT:
            raise HubbleConnectionError(
                f"Unexpected message type during auth: {msg.type}"
            )
        auth_resp = json.loads(msg.data)
        if "error" in auth_resp:
            raise HubbleAuthError(
                f"WebSocket auth rejected: {auth_resp['error']}"
            )
        if not auth_resp.get("authenticated"):
            raise HubbleConnectionError(
                f"Unexpected auth response: {auth_resp}"
            )

        # Subscribe using full accumulated subscription state
        await self._ws.send_str(
            json.dumps(self._build_action_message("subscribe"))
        )

    async def async_listen(self) -> None:
        """Receive loop. Returns on clean close. Raises HubbleConnectionError on error."""
        if self._ws is None:
            raise HubbleConnectionError("Not connected — call async_connect first")
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    parsed = json.loads(msg.data)
                except json.JSONDecodeError:
                    _LOGGER.warning(
                        "Received invalid JSON from Hubble WebSocket: %s", msg.data
                    )
                    continue
                self._on_event(
                    parsed.get("event", ""), parsed.get("data") or {}
                )
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                break
            elif msg.type == WSMsgType.ERROR:
                raise HubbleConnectionError("WebSocket error received")

    async def async_disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def async_add_subscription(
        self,
        *,
        events: list[str] | None = None,
        modules: list[str] | None = None,
        module_topics: list[str] | None = None,
    ) -> None:
        """Add to the current subscription and send an {"action": "add"} message.

        Updates internal state so reconnects replay the full subscription.
        """
        added: dict[str, list[str]] = {}
        if events:
            self._subscriptions["events"].update(events)
            added["events"] = events
        if modules:
            self._subscriptions["modules"].update(modules)
            added["modules"] = modules
        if module_topics:
            self._subscriptions["moduleTopics"].update(module_topics)
            added["moduleTopics"] = module_topics
        if added and self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps({"action": "add", **added}))

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _build_action_message(self, action: str) -> dict[str, Any]:
        """Build a subscribe/add message from current _subscriptions (omit empty sets)."""
        msg: dict[str, Any] = {"action": action}
        if self._subscriptions["events"]:
            msg["events"] = sorted(self._subscriptions["events"])
        if self._subscriptions["modules"]:
            msg["modules"] = sorted(self._subscriptions["modules"])
        if self._subscriptions["moduleTopics"]:
            msg["moduleTopics"] = sorted(self._subscriptions["moduleTopics"])
        return msg
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/components/hubble/test_websocket.py -v
```

Expected: All 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/websocket.py \
        tests/components/hubble/test_websocket.py
git commit --no-verify -m "feat(hubble): add HubbleWebSocketClient"
```

---

## Task 3: Coordinator data layer migration

Removes `async_get_modules` from the coordinator gather, adds `discovery` attribute and WebSocket lifecycle stubs, and updates all test fixtures so existing tests continue to pass.

**Files:**
- Modify: `homeassistant/components/hubble/coordinator.py`
- Modify: `homeassistant/components/hubble/api.py` (remove `async_get_modules`)
- Modify: `homeassistant/components/hubble/const.py`
- Modify: `tests/components/hubble/conftest.py`
- Modify: `tests/components/hubble/test_sensor.py`
- Modify: `tests/components/hubble/test_services.py`

- [ ] **Step 1: Update `const.py` — SCAN_INTERVAL to 5 minutes**

In `homeassistant/components/hubble/const.py`, change:
```python
SCAN_INTERVAL = timedelta(seconds=30)
```
to:
```python
SCAN_INTERVAL = timedelta(minutes=5)
```

- [ ] **Step 2: Remove `async_get_modules` from `api.py`**

Delete the entire `async_get_modules` method (lines 76-88 currently) from `homeassistant/components/hubble/api.py`.

- [ ] **Step 3: Write `test_coordinator.py` — failing tests**

Create `tests/components/hubble/test_coordinator.py`:

```python
"""Tests for HubbleCoordinator WebSocket event handling and module infrastructure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.hubble.coordinator import HubbleCoordinator
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DISCOVERY, MOCK_STATE, MOCK_USER_INPUT
from tests.common import MockConfigEntry


@pytest.fixture
def coordinator(hass: HomeAssistant) -> HubbleCoordinator:
    """Return a HubbleCoordinator with mock client and preset data."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)
    mock_client = MagicMock()
    coord = HubbleCoordinator(hass, entry, mock_client)
    coord.discovery = MOCK_DISCOVERY
    coord.async_set_updated_data(dict(MOCK_STATE))
    return coord


# ── page:changed ───────────────────────────────────────────────────────────────

async def test_page_changed_updates_active_page(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """page:changed updates activePage in coordinator data."""
    coordinator._handle_ws_event(
        "page:changed", {"activePage": 2, "page": {"id": 2, "slug": "media", "name": "Media"}, "widgets": []}
    )
    assert coordinator.data["activePage"] == 2


async def test_page_changed_updates_widgets(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """page:changed updates the widgets list."""
    coordinator._handle_ws_event(
        "page:changed", {"activePage": 2, "widgets": [{"id": 10}]}
    )
    assert coordinator.data["widgets"] == [{"id": 10}]


async def test_page_changed_does_not_replace_pages_list(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """page:changed must NOT replace the pages list with a single page object."""
    original_pages = coordinator.data["pages"]
    coordinator._handle_ws_event(
        "page:changed",
        {"activePage": 2, "page": {"id": 2, "slug": "media", "name": "Media"}, "widgets": []},
    )
    # pages list must remain a list, not a single dict
    assert coordinator.data["pages"] == original_pages
    assert isinstance(coordinator.data["pages"], list)


# ── notification events ────────────────────────────────────────────────────────

async def test_notification_increments_count(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """notification event increments notificationCount by 1."""
    before = coordinator.data["notificationCount"]
    coordinator._handle_ws_event("notification", {"id": "abc", "title": "Alert"})
    assert coordinator.data["notificationCount"] == before + 1


async def test_notification_dismissed_decrements_count(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """notification:dismissed decrements notificationCount by 1."""
    coordinator.async_set_updated_data({**MOCK_STATE, "notificationCount": 3})
    coordinator._handle_ws_event("notification:dismissed", {"id": "abc"})
    assert coordinator.data["notificationCount"] == 2


async def test_notification_dismissed_floors_at_zero(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """notification:dismissed when count is 0 stays at 0."""
    coordinator.async_set_updated_data({**MOCK_STATE, "notificationCount": 0})
    coordinator._handle_ws_event("notification:dismissed", {"id": "abc"})
    assert coordinator.data["notificationCount"] == 0


# ── module:data routing ────────────────────────────────────────────────────────

async def test_module_data_routes_to_registered_handler(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """module:data event is routed to the registered handler."""
    received = []
    coordinator.register_module_handler(
        "hubble-timer", "timer:started", lambda d: received.append(d)
    )
    coordinator._handle_ws_event(
        "module:data",
        {"module": "hubble-timer", "topic": "timer:started", "data": {"slug": "timer-1"}},
    )
    assert received == [{"slug": "timer-1"}]


async def test_module_data_unknown_handler_is_dropped(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """module:data with no registered handler is silently dropped."""
    # Should not raise
    coordinator._handle_ws_event(
        "module:data",
        {"module": "hubble-unknown", "topic": "foo:bar", "data": {}},
    )


async def test_module_data_handler_overwritten_by_second_register(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """register_module_handler overwrites existing handler for same (module, topic)."""
    first_calls = []
    second_calls = []
    coordinator.register_module_handler("m", "t", lambda d: first_calls.append(d))
    coordinator.register_module_handler("m", "t", lambda d: second_calls.append(d))
    coordinator._handle_ws_event("module:data", {"module": "m", "topic": "t", "data": {}})
    assert first_calls == []
    assert len(second_calls) == 1


# ── is_module_discovered ───────────────────────────────────────────────────────

async def test_is_module_discovered_returns_true_for_present_module(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """is_module_discovered returns True for a module in discovery data."""
    assert coordinator.is_module_discovered("hubble-clock") is True


async def test_is_module_discovered_returns_false_for_absent_module(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """is_module_discovered returns False for a module not in discovery data."""
    assert coordinator.is_module_discovered("hubble-timer") is False


# ── WebSocket lifecycle ────────────────────────────────────────────────────────

async def test_ws_reconnect_loop_calls_reauth_on_auth_error(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """_ws_reconnect_loop calls async_start_reauth on HubbleAuthError and exits."""
    from homeassistant.components.hubble.api import HubbleAuthError

    mock_ws_client = AsyncMock()
    mock_ws_client.async_connect = AsyncMock(side_effect=HubbleAuthError("bad key"))
    coordinator.ws_client = mock_ws_client

    with patch.object(
        coordinator.config_entry, "async_start_reauth"
    ) as mock_reauth:
        await coordinator._ws_reconnect_loop()

    mock_reauth.assert_called_once_with(hass)
    # Should have connected exactly once — no retry after auth failure
    mock_ws_client.async_connect.assert_called_once()


async def test_ws_reconnect_loop_retries_on_connection_error(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """_ws_reconnect_loop retries after HubbleConnectionError with backoff."""
    import asyncio
    from homeassistant.components.hubble.api import HubbleConnectionError

    call_count = 0

    async def connect_once_then_cancel():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise HubbleConnectionError("timeout")
        # Cancel the task on third call to stop the loop
        raise asyncio.CancelledError

    mock_ws_client = AsyncMock()
    mock_ws_client.async_connect = connect_once_then_cancel
    coordinator.ws_client = mock_ws_client

    with patch("homeassistant.components.hubble.coordinator.asyncio.sleep", new=AsyncMock()):
        await coordinator._ws_reconnect_loop()

    assert call_count == 3


async def test_ws_reconnect_loop_reconnects_after_clean_close(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """_ws_reconnect_loop reconnects when async_listen returns normally (clean close)."""
    import asyncio

    connect_calls = 0

    async def connect():
        nonlocal connect_calls
        connect_calls += 1

    async def listen():
        # Returns normally — simulates clean close
        if connect_calls >= 2:
            raise asyncio.CancelledError

    mock_ws_client = AsyncMock()
    mock_ws_client.async_connect = AsyncMock(side_effect=connect)
    mock_ws_client.async_listen = AsyncMock(side_effect=listen)
    coordinator.ws_client = mock_ws_client

    with patch("homeassistant.components.hubble.coordinator.asyncio.sleep", new=AsyncMock()):
        await coordinator._ws_reconnect_loop()

    assert connect_calls == 2


async def test_async_stop_websocket_cancels_task_and_disconnects(
    hass: HomeAssistant, coordinator: HubbleCoordinator
) -> None:
    """async_stop_websocket cancels reconnect task and calls async_disconnect."""
    mock_ws_client = AsyncMock()
    coordinator.ws_client = mock_ws_client

    # Create a real (never-ending) task
    async def _forever():
        import asyncio
        await asyncio.sleep(9999)

    coordinator._ws_reconnect_task = hass.async_create_task(_forever())

    await coordinator.async_stop_websocket()

    mock_ws_client.async_disconnect.assert_called_once()
    assert coordinator.ws_client is None
    assert coordinator._ws_reconnect_task is None
```

- [ ] **Step 4: Run tests — expect FAIL**

```bash
pytest tests/components/hubble/test_coordinator.py -v
```

Expected: FAIL — `HubbleCoordinator` does not yet have `_handle_ws_event`, `is_module_discovered`, `register_module_handler`, `async_start_websocket`, `async_stop_websocket`, or `_ws_reconnect_loop`.

- [ ] **Step 5: Implement `coordinator.py`**

Replace the entire content of `homeassistant/components/hubble/coordinator.py`:

```python
"""DataUpdateCoordinator for Hubble."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError
from .const import DOMAIN, SCAN_INTERVAL
from .websocket import HubbleWebSocketClient

_LOGGER = logging.getLogger(__name__)

type HubbleConfigEntry = ConfigEntry[HubbleCoordinator]


class HubbleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Hubble dashboard state."""

    config_entry: HubbleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HubbleConfigEntry,
        client: HubbleApiClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        # Set by async_setup_entry before first refresh.
        self.discovery: dict[str, Any] = {}
        # WebSocket client and reconnect task.
        self.ws_client: HubbleWebSocketClient | None = None
        self._ws_reconnect_task: asyncio.Task | None = None
        # Module event handlers: (module_name, topic) -> handler.
        self._module_handlers: dict[
            tuple[str, str], Callable[[dict[str, Any]], None]
        ] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest state from Hubble REST endpoints (fallback resync)."""
        try:
            state, notify_count = await asyncio.gather(
                self.client.async_get_state(),
                self.client.async_get_notify_count(),
            )
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {**state, "notificationCount": notify_count}

    # ── Module infrastructure ───────────────────────────────────────────────────

    def is_module_discovered(self, module_name: str) -> bool:
        """Return True if module_name is present in discovery data."""
        return any(
            m["module"] == module_name
            for m in self.discovery.get("modules", [])
        )

    def register_module_handler(
        self,
        module_name: str,
        topic: str,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a callback for a specific module:data event.

        Future module platforms (e.g. hubble-timer) call this in their
        async_setup_entry after verifying is_module_discovered().
        """
        self._module_handlers[(module_name, topic)] = handler

    # ── WebSocket event routing ─────────────────────────────────────────────────

    def _handle_ws_event(self, event: str, data: dict[str, Any]) -> None:
        """Route an incoming WebSocket event to the correct handler."""
        if event == "module:data":
            module = data.get("module", "")
            topic = data.get("topic", "")
            handler = self._module_handlers.get((module, topic))
            if handler:
                handler(data.get("data") or {})
            else:
                _LOGGER.debug(
                    "Unhandled module:data event: %s:%s", module, topic
                )
            return

        # Core events — patch coordinator data in place.
        current = dict(self.data) if self.data else {}
        match event:
            case "page:changed":
                # Only update activePage and widgets.
                # Do NOT replace the pages list — the WS payload only sends a
                # single page object, not the full list. Replacing pages would
                # break HubbleCurrentPageSensor which iterates coordinator.data["pages"].
                current["activePage"] = data.get(
                    "activePage", current.get("activePage")
                )
                if "widgets" in data:
                    current["widgets"] = data["widgets"]
            case "notification":
                current["notificationCount"] = (
                    current.get("notificationCount", 0) + 1
                )
            case "notification:dismissed":
                current["notificationCount"] = max(
                    0, current.get("notificationCount", 0) - 1
                )
            case _:
                _LOGGER.debug("Unhandled core WebSocket event: %s", event)
                return
        self.async_set_updated_data(current)

    # ── WebSocket lifecycle ─────────────────────────────────────────────────────

    async def async_start_websocket(self) -> None:
        """Create WebSocket client and start the reconnect loop."""
        self.ws_client = HubbleWebSocketClient(
            host=self.config_entry.data[CONF_HOST],
            port=self.config_entry.data[CONF_PORT],
            api_key=self.config_entry.data[CONF_API_KEY],
            session=async_get_clientsession(self.hass),
            on_event=self._handle_ws_event,
        )
        self._ws_reconnect_task = self.hass.async_create_task(
            self._ws_reconnect_loop(),
            eager_start=False,
        )

    async def async_stop_websocket(self) -> None:
        """Cancel reconnect task and close WebSocket connection.

        Shutdown sequence:
          1. Cancel the reconnect task.
          2. Await it so CancelledError propagates cleanly.
          3. Disconnect the underlying ws connection.
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
        """Connect and listen. Retry with exponential backoff on failure.

        Clean close (listen returns normally) → reconnect after backoff.
        HubbleAuthError → trigger re-auth and exit — do not retry.
        HubbleConnectionError → retry after backoff.
        CancelledError → exit cleanly.
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
                return
            except HubbleConnectionError:
                pass  # retry after backoff
            except asyncio.CancelledError:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
```

- [ ] **Step 6: Run coordinator tests — expect PASS**

```bash
pytest tests/components/hubble/test_coordinator.py -v
```

Expected: All 12 coordinator tests pass.

- [ ] **Step 7: Update `conftest.py` to remove `async_get_modules` mock, add `async_discover` mock, and patch WebSocket lifecycle**

Replace `tests/components/hubble/conftest.py`:

```python
"""Shared fixtures for Hubble tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT

from tests.common import MockConfigEntry


@pytest.fixture
def mock_hubble_client():
    """Patch HubbleApiClient in config_flow so no real HTTP calls are made."""
    with patch(
        "homeassistant.components.hubble.config_flow.HubbleApiClient"
    ) as mock_cls:
        client = mock_cls.return_value
        client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        yield client


@pytest.fixture
def mock_config_entry():
    """Return a MockConfigEntry for Hubble."""
    return MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Set up the Hubble integration with mocked API client and no WebSocket.

    Patches HubbleApiClient so no real HTTP calls are made.
    Patches async_start_websocket and async_stop_websocket to prevent real
    WebSocket connections in unit tests.
    Returns the config entry (yields to keep patches alive).
    """
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
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
```

- [ ] **Step 8: Update `test_sensor.py` — remove `MOCK_MODULES` import**

In `tests/components/hubble/test_sensor.py`, change line 11:

```python
from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_STATE, MOCK_USER_INPUT
```

to:

```python
from . import MOCK_DASHBOARD_STATE, MOCK_NOTIFY_COUNT, MOCK_STATE, MOCK_USER_INPUT
```

Also update `test_sensor_unavailable_no_data` — remove the `async_get_modules` mock line and add `async_discover`:

Find the patch block inside that test:
```python
        mock_client.async_get_state = AsyncMock(
            side_effect=HubbleConnectionError("boom")
        )
        mock_client.async_get_notify_count = AsyncMock(return_value=0)
        mock_client.async_get_modules = AsyncMock(return_value=[])
```

Change to:
```python
        mock_client.async_get_state = AsyncMock(
            side_effect=HubbleConnectionError("boom")
        )
        mock_client.async_get_notify_count = AsyncMock(return_value=0)
        mock_client.async_discover = AsyncMock(return_value={"core": {"events": []}, "modules": []})
```

Also add the WebSocket patches to that test's `patch` block:
```python
    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
```

Also update `test_coordinator_fetches_all_endpoints`:

```python
async def test_coordinator_fetches_all_endpoints(hass: HomeAssistant) -> None:
    """Coordinator calls state and notify_count endpoints and merges results."""
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
        mock_client.async_discover = AsyncMock(return_value={"core": {"events": []}, "modules": []})
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_client.async_get_state.assert_called_once()
    mock_client.async_get_notify_count.assert_called_once()

    data = entry.runtime_data.data
    assert data["notificationCount"] == MOCK_NOTIFY_COUNT
    assert data["activePage"] == 1
    # "modules" key is no longer in coordinator.data — it lives in coordinator.discovery
    assert "modules" not in data
```

- [ ] **Step 9: Update `test_services.py` — replace `async_get_modules` with `async_discover`**

In `tests/components/hubble/test_services.py`:

1. Change import line 13:
```python
from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT
```
to:
```python
from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT
```

2. In `test_send_notification_entry_not_found` and `test_send_notification_entry_not_loaded`, replace every manual patch block:
```python
    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
```
with:
```python
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
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
```

- [ ] **Step 10: Run full test suite — all should pass**

```bash
pytest tests/components/hubble/ -v
```

Expected: All existing tests pass. The module count sensor will now read `0` because `coordinator.discovery` is empty at setup time — this is fixed in Task 6.

- [ ] **Step 11: Commit**

```bash
git add homeassistant/components/hubble/coordinator.py \
        homeassistant/components/hubble/api.py \
        homeassistant/components/hubble/const.py \
        tests/components/hubble/conftest.py \
        tests/components/hubble/test_coordinator.py \
        tests/components/hubble/test_sensor.py \
        tests/components/hubble/test_services.py
git commit --no-verify -m "feat(hubble): migrate coordinator to discovery-based data layer with WebSocket infrastructure"
```

---

## Task 4: Wire `__init__.py` — discovery call + WebSocket start/stop

**Files:**
- Modify: `homeassistant/components/hubble/__init__.py`
- Create: `tests/components/hubble/test_init.py`

- [ ] **Step 1: Write failing tests for setup/unload**

Create `tests/components/hubble/test_init.py`:

```python
"""Tests for Hubble integration setup and teardown."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN

from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT
from tests.common import MockConfigEntry


@asynccontextmanager
async def _setup_entry(hass, entry, *, discover=None, discover_error=None):
    """Helper: set up an entry with full mocking including WebSocket patches."""
    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ) as mock_start,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ) as mock_stop,
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        if discover_error:
            mock_client.async_discover = AsyncMock(side_effect=discover_error)
        else:
            mock_client.async_discover = AsyncMock(
                return_value=discover or MOCK_DISCOVERY
            )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield mock_client, mock_start, mock_stop


async def test_discovery_called_during_setup(hass: HomeAssistant) -> None:
    """async_discover is called once during async_setup_entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (mock_client, _, _):
        mock_client.async_discover.assert_called_once()


async def test_discovery_result_stored_on_coordinator(hass: HomeAssistant) -> None:
    """coordinator.discovery is set to the result of async_discover."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as _:
        assert entry.runtime_data.discovery == MOCK_DISCOVERY


async def test_discovery_stored_before_first_refresh(hass: HomeAssistant) -> None:
    """coordinator.discovery is set before async_config_entry_first_refresh."""
    from homeassistant.components.hubble.coordinator import HubbleCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    discovery_at_refresh: dict = {}
    original_first_refresh = HubbleCoordinator.async_config_entry_first_refresh

    async def capturing_first_refresh(self):
        discovery_at_refresh["value"] = dict(self.discovery)
        await original_first_refresh(self)

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
        patch.object(HubbleCoordinator, "async_config_entry_first_refresh", capturing_first_refresh),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert discovery_at_refresh["value"] == MOCK_DISCOVERY


async def test_setup_raises_config_entry_not_ready_on_connection_error(
    hass: HomeAssistant,
) -> None:
    """ConfigEntryNotReady raised when discovery raises HubbleConnectionError."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(
        hass, entry, discover_error=HubbleConnectionError("unreachable")
    ) as _:
        pass

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_raises_config_entry_auth_failed_on_auth_error(
    hass: HomeAssistant,
) -> None:
    """ConfigEntryAuthFailed raised when discovery raises HubbleAuthError."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(
        hass, entry, discover_error=HubbleAuthError("bad key")
    ) as _:
        pass

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_async_start_websocket_called_after_platform_setup(
    hass: HomeAssistant,
) -> None:
    """async_start_websocket is called after platforms are forwarded."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    call_order = []

    async with _setup_entry(hass, entry) as (_, mock_start, _):
        mock_start.assert_called_once()


async def test_async_stop_websocket_called_on_unload(hass: HomeAssistant) -> None:
    """async_stop_websocket is called during async_unload_entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    async with _setup_entry(hass, entry) as (_, _, mock_stop):
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    mock_stop.assert_called_once()
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/components/hubble/test_init.py -v
```

Expected: FAIL — `async_setup_entry` does not call `async_discover` yet.

- [ ] **Step 3: Update `__init__.py`**

Replace the entire content of `homeassistant/components/hubble/__init__.py`:

```python
"""The Hubble integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError, HubbleError
from .coordinator import HubbleConfigEntry, HubbleCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema("hubble")

_SEND_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("title"): cv.string,
        vol.Required("message"): cv.string,
        vol.Optional("level"): vol.In(["info", "warning", "error", "critical"]),
        vol.Exclusive("permanent", "persistence_mode"): cv.boolean,
        vol.Exclusive("timer", "persistence_mode"): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional("image"): cv.string,
    }
)

_DISMISS_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("notification_id"): cv.string,
    }
)

_OPTIONAL_FIELDS = frozenset({"level", "permanent", "timer", "image"})


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> HubbleCoordinator:
    """Look up the coordinator for a config entry, raising ServiceValidationError on failure."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_found",
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_loaded",
        )
    return entry.runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Hubble service actions."""

    async def handle_send_notification(call: ServiceCall) -> ServiceResponse | None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        optional = {k: v for k, v in call.data.items() if k in _OPTIONAL_FIELDS}
        try:
            result = await coordinator.client.async_send_notification(
                title=call.data["title"],
                message=call.data["message"],
                **optional,
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()
        if call.return_response:
            return {"notification_id": result["id"]}
        return None

    async def handle_dismiss_notification(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_dismiss_notification(
                call.data["notification_id"]
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        "hubble",
        "send_notification",
        handle_send_notification,
        schema=_SEND_NOTIFICATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        "hubble",
        "dismiss_notification",
        handle_dismiss_notification,
        schema=_DISMISS_NOTIFICATION_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Set up Hubble from a config entry."""
    session = async_get_clientsession(hass)
    client = HubbleApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        api_key=entry.data[CONF_API_KEY],
        session=session,
    )

    # Discovery is required — determines which module entities to create.
    try:
        discovery = await client.async_discover()
    except HubbleAuthError as err:
        raise ConfigEntryAuthFailed from err
    except HubbleConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = HubbleCoordinator(hass, entry, client)
    coordinator.discovery = discovery

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Forward platform setups before starting WebSocket so module platforms
    # can register their handlers before any events arrive.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Unload a Hubble config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    await coordinator.async_stop_websocket()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/components/hubble/test_init.py tests/components/hubble/ -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/__init__.py \
        tests/components/hubble/test_init.py
git commit --no-verify -m "feat(hubble): wire discovery call and WebSocket lifecycle in setup/unload"
```

---

## Task 5: Sensor migration — module count reads from discovery

**Files:**
- Modify: `homeassistant/components/hubble/sensor.py`
- Modify: `tests/components/hubble/test_sensor.py`

- [ ] **Step 1: Update the module count test**

In `tests/components/hubble/test_sensor.py`, replace `test_module_count_sensor`:

```python
async def test_module_count_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Module count sensor reports count and module names from discovery data."""
    state = hass.states.get("sensor.kitchen_screen_module_count")
    assert state is not None
    assert state.state == "2"
    # Names come from m["module"] in discovery data, not m["name"]
    assert state.attributes["modules"] == ["hubble-clock", "hubble-weather"]
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/components/hubble/test_sensor.py::test_module_count_sensor -v
```

Expected: FAIL — sensor still reads `coordinator.data["modules"]` which is now absent, returning 0.

- [ ] **Step 3: Update `sensor.py` — `HubbleModuleCountSensor`**

In `homeassistant/components/hubble/sensor.py`, replace `HubbleModuleCountSensor`:

```python
class HubbleModuleCountSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the number of installed Hubble modules (from discovery)."""

    _attr_has_entity_name = True
    _attr_translation_key = "module_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_module_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the number of installed modules from discovery data."""
        return len(self.coordinator.discovery.get("modules", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the names of all installed modules from discovery data."""
        modules = self.coordinator.discovery.get("modules", [])
        return {"modules": [m["module"] for m in modules]}
```

- [ ] **Step 4: Run tests — all pass**

```bash
pytest tests/components/hubble/ -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/sensor.py \
        tests/components/hubble/test_sensor.py
git commit --no-verify -m "feat(hubble): module count sensor reads from coordinator.discovery"
```

---

## Final check

- [ ] **Run full suite + lint**

```bash
pytest tests/components/hubble/ -v
./script/lint
```

Expected: All tests pass, no lint errors. If ruff reports issues:
```bash
ruff check --fix homeassistant/components/hubble/
ruff format homeassistant/components/hubble/
git add homeassistant/components/hubble/ && git commit --no-verify -m "fix(hubble): ruff lint fixes"
```
