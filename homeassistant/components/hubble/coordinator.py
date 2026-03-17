"""DataUpdateCoordinator for Hubble."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type HubbleConfigEntry = ConfigEntry[HubbleCoordinator]


class HubbleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Hubble dashboard state."""

    config_entry: HubbleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HubbleConfigEntry,
        client: HubbleApiClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest state from Hubble."""
        try:
            return await self.client.async_get_state()
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(f"Cannot connect to Hubble: {err}") from err
