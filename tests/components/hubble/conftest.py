"""Shared fixtures for Hubble tests."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT

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
    """Set up the Hubble integration with a mocked API client.

    Patches the HubbleApiClient used by __init__.py so no real HTTP calls
    are made. Returns the config entry.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_get_modules = AsyncMock(return_value=[])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry
