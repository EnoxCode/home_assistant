"""Shared fixtures for Hubble tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import (
    MOCK_COMMAND_EXECUTE_RESULT,
    MOCK_DASHBOARD_STATE,
    MOCK_DISCOVERY,
    MOCK_MEDIA_STATE,
    MOCK_NOTIFY_COUNT,
    MOCK_USER_INPUT,
)

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
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            return_value=dict(MOCK_MEDIA_STATE)
        )
        mock_client.async_execute_command = AsyncMock(
            return_value=dict(MOCK_COMMAND_EXECUTE_RESULT)
        )
        mock_client.async_select_widget = AsyncMock(return_value={"widgetId": 5})
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
