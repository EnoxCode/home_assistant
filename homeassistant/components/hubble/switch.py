"""Hubble screen switch entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HubbleError
from .const import (
    CONF_SCREEN_OFF_COMMAND,
    CONF_SCREEN_ON_COMMAND,
    DEFAULT_SCREEN_OFF_COMMAND,
    DEFAULT_SCREEN_ON_COMMAND,
    DOMAIN,
)
from .coordinator import HubbleConfigEntry, HubbleCoordinator, HubbleScreenCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble screen switch entity."""
    coordinator = entry.runtime_data
    if coordinator.screen_coordinator is None:
        return
    async_add_entities(
        [HubbleScreenSwitch(coordinator.screen_coordinator, coordinator, entry)]
    )


class HubbleScreenSwitch(CoordinatorEntity[HubbleScreenCoordinator], SwitchEntity):
    """Switch entity that controls display power via the commands API."""

    _attr_has_entity_name = True
    _attr_translation_key = "hubble_screen"

    def __init__(
        self,
        coordinator: HubbleScreenCoordinator,
        main_coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the screen switch."""
        super().__init__(coordinator)
        self._main_coordinator = main_coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_screen"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )

    @property
    def is_on(self) -> bool | None:
        """Return True when the screen is on."""
        return self.coordinator.data

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the screen on."""
        slug = self._entry.data.get(CONF_SCREEN_ON_COMMAND, DEFAULT_SCREEN_ON_COMMAND)
        try:
            await self._main_coordinator.client.async_execute_command(slug)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the screen off."""
        slug = self._entry.data.get(CONF_SCREEN_OFF_COMMAND, DEFAULT_SCREEN_OFF_COMMAND)
        try:
            await self._main_coordinator.client.async_execute_command(slug)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
