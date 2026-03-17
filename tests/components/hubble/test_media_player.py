"""Tests for Hubble media player and display mode select entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

from . import (
    MOCK_DASHBOARD_STATE,
    MOCK_DISCOVERY,
    MOCK_MEDIA_STATE,
    MOCK_NOTIFY_COUNT,
    MOCK_USER_INPUT,
)


@pytest.fixture
async def setup_media_player(hass: HomeAssistant):
    """Set up Hubble integration with a mocked media player state.

    Returns the config entry. All API calls are mocked; WebSocket is suppressed.
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
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            return_value=dict(MOCK_MEDIA_STATE)
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock_client


# ── Platform setup ────────────────────────────────────────────────────────────


async def test_media_player_entity_created(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform creates a media_player entity."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state is not None


async def test_display_mode_select_entity_created(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform creates a display_mode select entity alongside the media player."""
    state = hass.states.get("select.kitchen_screen_display_mode")
    assert state is not None


async def test_initial_state_fetched(hass: HomeAssistant, setup_media_player) -> None:
    """async_media_get_state is called once during setup."""
    entry, mock_client = setup_media_player
    mock_client.async_media_get_state.assert_called_once()


async def test_media_state_handler_registered_on_coordinator(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform registers a 'media:state' core handler on the coordinator."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    assert "media:state" in coordinator._core_handlers


async def test_entities_unavailable_when_initial_fetch_fails(
    hass: HomeAssistant,
) -> None:
    """Both entities start unavailable when async_media_get_state raises."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
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
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            side_effect=HubbleConnectionError("timeout")
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    player = hass.states.get("media_player.kitchen_screen_media_player")
    display = hass.states.get("select.kitchen_screen_display_mode")
    assert player is not None
    assert player.state == STATE_UNAVAILABLE
    assert display is not None
    assert display.state == STATE_UNAVAILABLE
