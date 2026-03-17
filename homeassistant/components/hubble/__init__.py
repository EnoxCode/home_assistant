"""The Hubble integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv, selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError, HubbleError
from .coordinator import HubbleConfigEntry, HubbleCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema("hubble")

_SEND_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("title"): cv.string,
        vol.Required("message"): cv.string,
        vol.Optional("level"): vol.In(["info", "warning", "error", "critical"]),
        vol.Exclusive("permanent", "persistence_mode"): cv.boolean,
        vol.Exclusive("timer", "persistence_mode"): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional("image"): cv.string,
    }
)

_DISMISS_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry_id"): selector.ConfigEntrySelector(
            {"integration": "hubble"}
        ),
        vol.Required("notification_id"): cv.string,
    }
)

_OPTIONAL_FIELDS = frozenset({"level", "permanent", "timer", "image"})


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> HubbleCoordinator:
    """Look up the coordinator for a config entry, raising ServiceValidationError on failure."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_found",
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain="hubble",
            translation_key="config_entry_not_loaded",
        )
    return entry.runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register Hubble service actions."""

    async def handle_send_notification(call: ServiceCall) -> ServiceResponse | None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        optional = {k: v for k, v in call.data.items() if k in _OPTIONAL_FIELDS}
        try:
            result = await coordinator.client.async_send_notification(
                title=call.data["title"],
                message=call.data["message"],
                **optional,
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()
        if call.return_response:
            return {"notification_id": result["id"]}
        return None

    async def handle_dismiss_notification(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["config_entry_id"])
        try:
            await coordinator.client.async_dismiss_notification(
                call.data["notification_id"]
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await coordinator.async_request_refresh()

    hass.services.async_register(
        "hubble",
        "send_notification",
        handle_send_notification,
        schema=_SEND_NOTIFICATION_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        "hubble",
        "dismiss_notification",
        handle_dismiss_notification,
        schema=_DISMISS_NOTIFICATION_SCHEMA,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Set up Hubble from a config entry."""
    session = async_get_clientsession(hass)
    client = HubbleApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        api_key=entry.data[CONF_API_KEY],
        session=session,
    )

    # Discovery is required — determines which module entities to create.
    try:
        discovery = await client.async_discover()
    except HubbleAuthError as err:
        raise ConfigEntryAuthFailed from err
    except HubbleConnectionError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = HubbleCoordinator(hass, entry, client)
    coordinator.discovery = discovery

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Forward platform setups before starting WebSocket so module platforms
    # can register their handlers before any events arrive.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.async_start_websocket()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Unload a Hubble config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    await coordinator.async_stop_websocket()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
