"""Tests for Hubble screen switch entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import (
    MOCK_COMMAND_EXECUTE_RESULT,
    MOCK_DASHBOARD_STATE,
    MOCK_DISCOVERY,
    MOCK_MEDIA_STATE,
    MOCK_NOTIFY_COUNT,
    MOCK_USER_INPUT,
)

from tests.common import MockConfigEntry

SWITCH_ENTITY_ID = "switch.kitchen_screen_screen"


@pytest.fixture
async def setup_switch(hass: HomeAssistant):
    """Set up Hubble integration with a mocked screen switch.

    Returns (entry, mock_client). Screen status defaults to 'true' (on).
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock_client


# ── Platform setup ────────────────────────────────────────────────────────────


async def test_switch_entity_created(hass: HomeAssistant, setup_switch) -> None:
    """Platform creates a switch entity for screen control."""
    state = hass.states.get(SWITCH_ENTITY_ID)
    assert state is not None


async def test_switch_initial_state_on(hass: HomeAssistant, setup_switch) -> None:
    """Switch reports ON when screen-status stdout is 'true'."""
    state = hass.states.get(SWITCH_ENTITY_ID)
    assert state.state == STATE_ON


async def test_switch_initial_state_off(hass: HomeAssistant) -> None:
    """Switch reports OFF when screen-status stdout is 'false'."""
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
            return_value=dict(MOCK_MEDIA_STATE)
        )
        mock_client.async_execute_command = AsyncMock(
            return_value={
                "ok": True,
                "stdout": "false",
                "stderr": "",
                "exitCode": 0,
            }
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(SWITCH_ENTITY_ID)
    assert state.state == STATE_OFF


# ── Service calls ─────────────────────────────────────────────────────────────


async def test_turn_on_executes_screen_on_command(
    hass: HomeAssistant, setup_switch
) -> None:
    """turn_on calls GET /api/commands/screen-on/execute."""
    entry, mock_client = setup_switch
    mock_client.async_execute_command = AsyncMock(
        return_value={"ok": True, "stdout": "true", "stderr": "", "exitCode": 0}
    )
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": SWITCH_ENTITY_ID},
        blocking=True,
    )
    mock_client.async_execute_command.assert_any_call("screen-on")


async def test_turn_off_executes_screen_off_command(
    hass: HomeAssistant, setup_switch
) -> None:
    """turn_off calls GET /api/commands/screen-off/execute."""
    entry, mock_client = setup_switch
    mock_client.async_execute_command = AsyncMock(
        return_value={"ok": True, "stdout": "false", "stderr": "", "exitCode": 0}
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": SWITCH_ENTITY_ID},
        blocking=True,
    )
    mock_client.async_execute_command.assert_any_call("screen-off")


async def test_turn_on_error_raises_home_assistant_error(
    hass: HomeAssistant, setup_switch
) -> None:
    """HubbleError during turn_on surfaces as HomeAssistantError."""
    entry, mock_client = setup_switch
    mock_client.async_execute_command = AsyncMock(
        side_effect=HubbleConnectionError("timeout")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": SWITCH_ENTITY_ID},
            blocking=True,
        )


async def test_turn_off_error_raises_home_assistant_error(
    hass: HomeAssistant, setup_switch
) -> None:
    """HubbleError during turn_off surfaces as HomeAssistantError."""
    entry, mock_client = setup_switch
    mock_client.async_execute_command = AsyncMock(
        side_effect=HubbleConnectionError("timeout")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": SWITCH_ENTITY_ID},
            blocking=True,
        )


# ── WS event: screen:changed ──────────────────────────────────────────────────


async def test_screen_changed_event_triggers_refresh(
    hass: HomeAssistant, setup_switch
) -> None:
    """screen:changed WS event schedules an immediate screen-status poll."""
    entry, mock_client = setup_switch
    coordinator = entry.runtime_data

    # Track how many times screen-status is polled
    initial_call_count = mock_client.async_execute_command.call_count

    coordinator._handle_ws_event("screen:changed", {})
    await hass.async_block_till_done()

    # At least one more execute_command call should have been made
    assert mock_client.async_execute_command.call_count > initial_call_count


async def test_screen_changed_event_updates_state_to_off(
    hass: HomeAssistant, setup_switch
) -> None:
    """After screen:changed, switch reflects the refreshed screen state."""
    entry, mock_client = setup_switch
    coordinator = entry.runtime_data

    # Override execute_command to return screen=off on the next poll
    mock_client.async_execute_command = AsyncMock(
        return_value={"ok": True, "stdout": "false", "stderr": "", "exitCode": 0}
    )
    coordinator._handle_ws_event("screen:changed", {})
    await hass.async_block_till_done()

    state = hass.states.get(SWITCH_ENTITY_ID)
    assert state.state == STATE_OFF


# ── Unavailable state ─────────────────────────────────────────────────────────


async def test_switch_unavailable_when_status_fails(hass: HomeAssistant) -> None:
    """Switch starts unavailable when screen-status command fails."""
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
            return_value=dict(MOCK_MEDIA_STATE)
        )
        # Screen status always fails
        mock_client.async_execute_command = AsyncMock(
            side_effect=HubbleConnectionError("no screen")
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(SWITCH_ENTITY_ID)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE
