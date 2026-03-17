"""Tests for HubbleCoordinator WebSocket event handling and module infrastructure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.components.hubble.coordinator import HubbleCoordinator
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
    """Notification event increments notificationCount by 1."""
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
