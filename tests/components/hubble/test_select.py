"""Tests for the Hubble select platform."""

from unittest.mock import AsyncMock

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.websocket import _DEFAULT_EVENTS
from homeassistant.core import HomeAssistant

from . import MOCK_DISCOVERY, MOCK_STATE


async def test_select_options_are_page_slugs(
    hass: HomeAssistant, setup_integration
) -> None:
    """Select options are page slugs from coordinator data."""
    state = hass.states.get("select.kitchen_screen_active_page")
    assert state is not None
    assert state.state == "home"
    assert state.attributes["options"] == ["home", "media"]
    assert state.attributes["page_name"] == "Home"


async def test_select_current_option_tracks_active_page(
    hass: HomeAssistant, setup_integration
) -> None:
    """Current option updates when coordinator pushes new activePage."""
    coordinator = setup_integration.runtime_data
    coordinator.async_set_updated_data({**MOCK_STATE, "activePage": 2})
    await hass.async_block_till_done()

    state = hass.states.get("select.kitchen_screen_active_page")
    assert state.state == "media"
    assert state.attributes["page_name"] == "Media"


async def test_select_option_calls_set_active_page(
    hass: HomeAssistant, setup_integration
) -> None:
    """Selecting an option calls async_set_active_page with correct page ID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_set_active_page = AsyncMock(
        return_value={"success": True, "activePage": 2}
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.kitchen_screen_active_page",
            "option": "media",
        },
        blocking=True,
    )

    coordinator.client.async_set_active_page.assert_called_once_with(2)


async def test_select_unknown_option_does_not_call_api(
    hass: HomeAssistant, setup_integration
) -> None:
    """Selecting an unknown slug silently does nothing."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_set_active_page = AsyncMock()

    # HA's select platform validates options before calling async_select_option,
    # so we test by directly calling the entity method
    entity = next(
        e
        for e in hass.data["entity_components"]["select"].entities
        if e.unique_id and "active_page" in e.unique_id
    )
    await entity.async_select_option("nonexistent-slug")
    coordinator.client.async_set_active_page.assert_not_called()


async def test_ws_client_default_events_include_widget_events(
    hass: HomeAssistant, setup_integration
) -> None:
    """widget:selected, widget:added, widget:removed are in _DEFAULT_EVENTS."""
    assert "widget:selected" in _DEFAULT_EVENTS
    assert "widget:added" in _DEFAULT_EVENTS
    assert "widget:removed" in _DEFAULT_EVENTS


async def test_coordinator_widget_added_triggers_discovery_refresh(
    hass: HomeAssistant, setup_integration
) -> None:
    """widget:added WS event causes coordinator to re-fetch discovery."""
    coordinator = setup_integration.runtime_data
    new_discovery = {
        **MOCK_DISCOVERY,
        "selectableWidgets": [
            {
                "widgetId": 99,
                "pageId": 1,
                "visualization": "clock",
                "title": "New Widget",
            },
        ],
    }
    coordinator.client.async_discover = AsyncMock(return_value=new_discovery)

    coordinator._handle_ws_event("widget:added", {"widgetId": 99})
    await hass.async_block_till_done()

    assert coordinator.discovery["selectableWidgets"][0]["widgetId"] == 99


async def test_coordinator_widget_removed_triggers_discovery_refresh(
    hass: HomeAssistant, setup_integration
) -> None:
    """widget:removed WS event causes coordinator to re-fetch discovery."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_discover = AsyncMock(
        return_value={**MOCK_DISCOVERY, "selectableWidgets": []}
    )

    coordinator._handle_ws_event("widget:removed", {"widgetId": 5})
    await hass.async_block_till_done()

    assert coordinator.discovery["selectableWidgets"] == []


async def test_coordinator_discovery_refresh_failure_does_not_raise(
    hass: HomeAssistant, setup_integration
) -> None:
    """Discovery refresh failure logs an error and does not raise or crash."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_discover = AsyncMock(
        side_effect=HubbleConnectionError("unreachable")
    )

    coordinator._handle_ws_event("widget:added", {})
    await hass.async_block_till_done()
    # No exception — test passes if we get here
