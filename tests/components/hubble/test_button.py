"""Tests for the Hubble button platform."""

from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant


@pytest.mark.parametrize(
    ("entity_id", "method_name"),
    [
        ("button.kitchen_screen_next_page", "async_next_page"),
        ("button.kitchen_screen_previous_page", "async_previous_page"),
        ("button.kitchen_screen_next_widget", "async_next_widget"),
        ("button.kitchen_screen_previous_widget", "async_previous_widget"),
        (
            "button.kitchen_screen_dismiss_all_notifications",
            "async_dismiss_all_notifications",
        ),
        ("button.kitchen_screen_refresh_dashboard", "async_refresh_dashboard"),
    ],
)
async def test_button_press(
    hass: HomeAssistant,
    setup_integration,
    entity_id: str,
    method_name: str,
) -> None:
    """Each button calls the correct API method on press."""
    coordinator = setup_integration.runtime_data

    state = hass.states.get(entity_id)
    assert state is not None

    # Mock the specific API method on the coordinator's client
    mock_method = AsyncMock(return_value={"ok": True})
    setattr(coordinator.client, method_name, mock_method)
    # Patch coordinator refresh to verify it's called after press
    coordinator.async_request_refresh = AsyncMock()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": entity_id},
        blocking=True,
    )

    mock_method.assert_called_once()
    coordinator.async_request_refresh.assert_called_once()


async def test_next_widget_204_does_not_raise(
    hass: HomeAssistant, setup_integration
) -> None:
    """Pressing next_widget when no widgets exist (returns None) does not raise."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_next_widget = AsyncMock(return_value=None)
    coordinator.async_request_refresh = AsyncMock()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kitchen_screen_next_widget"},
        blocking=True,
    )

    coordinator.client.async_next_widget.assert_called_once()
    coordinator.async_request_refresh.assert_called_once()


async def test_command_button_created(
    hass: HomeAssistant,
    setup_integration,
) -> None:
    """A non-builtin command from discovery creates a button entity."""
    state = hass.states.get("button.kitchen_screen_test_command")
    assert state is not None


async def test_command_button_press(
    hass: HomeAssistant,
    setup_integration,
) -> None:
    """Pressing a command button calls async_execute_command with the correct slug."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_execute_command = AsyncMock(return_value={"ok": True})
    coordinator.async_request_refresh = AsyncMock()

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.kitchen_screen_test_command"},
        blocking=True,
    )

    coordinator.client.async_execute_command.assert_called_once_with("test-command")
    coordinator.async_request_refresh.assert_called_once()


async def test_builtin_commands_not_exposed_as_buttons(
    hass: HomeAssistant,
    setup_integration,
) -> None:
    """Builtin commands do not get button entities."""
    assert hass.states.get("button.kitchen_screen_screen_off") is None
    assert hass.states.get("button.kitchen_screen_screen_on") is None
    assert hass.states.get("button.kitchen_screen_screen_status") is None
