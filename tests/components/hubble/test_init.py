"""Tests for Hubble integration setup and teardown."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT

from tests.common import MockConfigEntry


@asynccontextmanager
async def _setup_entry(hass, entry, *, discover=None, discover_error=None):
    """Set up an entry with full mocking including WebSocket patches."""
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
        patch.object(
            HubbleCoordinator,
            "async_config_entry_first_refresh",
            capturing_first_refresh,
        ),
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
