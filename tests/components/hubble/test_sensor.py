"""Tests for the Hubble sensor platform."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_STATE, MOCK_USER_INPUT

from tests.common import MockConfigEntry


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    """Set up the Hubble integration with a mocked coordinator."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Hubble (kitchen-screen:3000)",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_STATE)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_sensor_state(hass: HomeAssistant, setup_integration) -> None:
    """Sensor state is the name of the active page."""
    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    assert state is not None
    assert state.state == "Home"
    assert state.attributes["slug"] == "home"
    assert state.attributes["id"] == 1


async def test_sensor_unavailable_no_data(hass: HomeAssistant) -> None:
    """Entry fails to load when first refresh raises — sensor entity does not exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Hubble (kitchen-screen:3000)",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.async_get_state = AsyncMock(side_effect=Exception("boom"))
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    # Entry won't load when first refresh fails — sensor won't exist
    assert state is None


async def test_sensor_unavailable_page_not_found(
    hass: HomeAssistant, setup_integration
) -> None:
    """Sensor is unavailable when activePage id is not in pages list."""
    entry = setup_integration
    coordinator = entry.runtime_data

    bad_state = {**MOCK_STATE, "activePage": 999}
    coordinator.async_set_updated_data(bad_state)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.hubble_kitchen_screen_3000_current_page")
    assert state is not None
    assert state.state == "unavailable"
