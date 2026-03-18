"""Tests for Hubble service actions."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT

from tests.common import MockConfigEntry


async def test_send_notification_returns_id(
    hass: HomeAssistant, setup_integration
) -> None:
    """send_notification returns the notification UUID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_send_notification = AsyncMock(
        return_value={"id": "abc-123", "success": True}
    )

    result = await hass.services.async_call(
        DOMAIN,
        "send_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "title": "Motion Detected",
            "message": "Camera triggered",
        },
        return_response=True,
        blocking=True,
    )

    assert result == {"notification_id": "abc-123"}
    coordinator.client.async_send_notification.assert_called_once_with(
        title="Motion Detected",
        message="Camera triggered",
    )


async def test_send_notification_with_optional_fields(
    hass: HomeAssistant, setup_integration
) -> None:
    """send_notification passes optional fields to the API."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_send_notification = AsyncMock(
        return_value={"id": "def-456", "success": True}
    )

    await hass.services.async_call(
        DOMAIN,
        "send_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "title": "Alert",
            "message": "Something happened",
            "level": "warning",
            "permanent": True,
        },
        blocking=True,
    )

    coordinator.client.async_send_notification.assert_called_once_with(
        title="Alert",
        message="Something happened",
        level="warning",
        permanent=True,
    )


async def test_dismiss_notification_calls_api(
    hass: HomeAssistant, setup_integration
) -> None:
    """dismiss_notification calls async_dismiss_notification with the UUID."""
    coordinator = setup_integration.runtime_data
    coordinator.client.async_dismiss_notification = AsyncMock(
        return_value={"success": True}
    )

    await hass.services.async_call(
        DOMAIN,
        "dismiss_notification",
        {
            "config_entry_id": setup_integration.entry_id,
            "notification_id": "abc-123",
        },
        blocking=True,
    )

    coordinator.client.async_dismiss_notification.assert_called_once_with("abc-123")


async def test_send_notification_entry_not_found(hass: HomeAssistant) -> None:
    """send_notification raises ServiceValidationError for unknown entry_id."""
    # Register domain by setting up any entry, then use a fake entry_id
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_notification",
            {
                "config_entry_id": "nonexistent-entry-id",
                "title": "Test",
                "message": "Test",
            },
            blocking=True,
        )


async def test_send_notification_entry_not_loaded(hass: HomeAssistant) -> None:
    """send_notification raises ServiceValidationError when entry exists but is not loaded."""
    # Load domain (so async_setup runs and services are registered) via a first entry
    other_entry = MockConfigEntry(
        domain=DOMAIN, data=MOCK_USER_INPUT, title="Other Screen"
    )
    other_entry.add_to_hass(hass)
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
        await hass.config_entries.async_setup(other_entry.entry_id)
        await hass.async_block_till_done()

    # Add entry AFTER domain is loaded so it won't be auto-set-up — state is NOT_LOADED
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "send_notification",
            {
                "config_entry_id": entry.entry_id,
                "title": "Test",
                "message": "Test",
            },
            blocking=True,
        )
