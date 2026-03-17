"""Tests for the Hubble sensor platform."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant

from . import MOCK_DASHBOARD_STATE, MOCK_MODULES, MOCK_NOTIFY_COUNT, MOCK_STATE, MOCK_USER_INPUT

from tests.common import MockConfigEntry


async def test_sensor_state(hass: HomeAssistant, setup_integration) -> None:
    """Sensor state is the name of the active page."""
    state = hass.states.get("sensor.kitchen_screen_current_page")
    assert state is not None
    assert state.state == "Home"
    assert state.attributes["slug"] == "home"
    assert state.attributes["id"] == 1


async def test_sensor_unavailable_no_data(hass: HomeAssistant) -> None:
    """Entry fails to load when first refresh raises — sensor entity does not exist."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(
            side_effect=HubbleConnectionError("boom")
        )
        mock_client.async_get_notify_count = AsyncMock(return_value=0)
        mock_client.async_get_modules = AsyncMock(return_value=[])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_current_page")
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

    state = hass.states.get("sensor.kitchen_screen_current_page")
    assert state is not None
    assert state.state == "unavailable"


async def test_coordinator_fetches_all_endpoints(hass: HomeAssistant) -> None:
    """Coordinator calls all three API methods and merges results."""
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
        mock_client.async_get_modules = AsyncMock(return_value=MOCK_MODULES)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_client.async_get_state.assert_called_once()
    mock_client.async_get_notify_count.assert_called_once()
    mock_client.async_get_modules.assert_called_once()

    data = entry.runtime_data.data
    assert data["notificationCount"] == MOCK_NOTIFY_COUNT
    assert data["modules"] == MOCK_MODULES
    assert data["activePage"] == 1


async def test_module_count_sensor(hass: HomeAssistant, setup_integration) -> None:
    """Module count sensor reports count and module names in attributes."""
    state = hass.states.get("sensor.kitchen_screen_module_count")
    assert state is not None
    assert state.state == "2"
    assert state.attributes["modules"] == ["hubble-clock", "hubble-weather"]


async def test_notification_count_sensor(
    hass: HomeAssistant, setup_integration
) -> None:
    """Notification count sensor reports the active notification count."""
    state = hass.states.get("sensor.kitchen_screen_notification_count")
    assert state is not None
    assert state.state == "2"


async def test_notification_count_updates(
    hass: HomeAssistant, setup_integration
) -> None:
    """Notification count sensor updates when coordinator data changes."""
    coordinator = setup_integration.runtime_data
    coordinator.async_set_updated_data({**MOCK_STATE, "notificationCount": 0})
    await hass.async_block_till_done()

    state = hass.states.get("sensor.kitchen_screen_notification_count")
    assert state.state == "0"
