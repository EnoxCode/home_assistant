"""The Hubble integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HubbleApiClient
from .coordinator import HubbleConfigEntry, HubbleCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Set up Hubble from a config entry."""
    session = async_get_clientsession(hass)
    client = HubbleApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        api_key=entry.data[CONF_API_KEY],
        session=session,
    )
    coordinator = HubbleCoordinator(hass, entry, client)
    # UpdateFailed is automatically converted to ConfigEntryNotReady here,
    # scheduling a retry — no explicit try/except needed.
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HubbleConfigEntry) -> bool:
    """Unload a Hubble config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
