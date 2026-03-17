"""Tests for the Hubble config flow."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from . import MOCK_STATE, MOCK_USER_INPUT


async def test_user_flow_success(hass: HomeAssistant, mock_hubble_client) -> None:
    """Happy path: valid credentials create a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "homeassistant.components.hubble.HubbleCoordinator"
    ) as mock_coordinator_cls:
        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_config_entry_first_refresh = AsyncMock()
        mock_coordinator.data = MOCK_STATE

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input=MOCK_USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hubble (kitchen-screen:3000)"
    assert result["data"] == MOCK_USER_INPUT


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (HubbleAuthError, "invalid_auth"),
        (HubbleConnectionError, "cannot_connect"),
        (Exception, "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_hubble_client,
    side_effect,
    expected_error,
) -> None:
    """Errors during validation show correct inline error."""
    mock_hubble_client.async_get_state.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected_error}


async def test_user_flow_duplicate(
    hass: HomeAssistant, mock_hubble_client, mock_config_entry
) -> None:
    """Duplicate host+port aborts with already_configured."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=MOCK_USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_success(
    hass: HomeAssistant, mock_hubble_client, mock_config_entry
) -> None:
    """Re-auth with a new API key updates the entry."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_API_KEY: "new-api-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_API_KEY] == "new-api-key"
