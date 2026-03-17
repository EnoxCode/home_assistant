"""Hubble select platform — active page selector and display mode selector."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HubbleError
from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator

_LOGGER = logging.getLogger(__name__)

DISPLAY_MODES = [
    "fullscreen",
    "half-top",
    "half-bottom",
    "quarter-tl",
    "quarter-tr",
    "quarter-bl",
    "quarter-br",
    "none",
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble select entities from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data

    # Fetch initial media state and store on coordinator for sharing with the
    # media_player platform (which sets up after select due to HA dependency order).
    if coordinator.media_state is None:
        try:
            coordinator.media_state = await coordinator.client.async_media_get_state()
        except HubbleError:
            _LOGGER.warning("Failed to fetch initial Hubble media player state")
            coordinator.media_state = None

    display = HubbleDisplayModeSelect(coordinator, entry)
    coordinator.display_mode_entity = display

    # Register the media:state core handler. It updates the shared media_state dict
    # and writes state to both the display mode select and the media player entity
    # (the latter is stored on coordinator.media_player_entity after media_player
    # platform setup completes).
    def on_media_state(data: dict[str, Any]) -> None:
        if coordinator.media_state is None:
            coordinator.media_state = data.copy()
        else:
            coordinator.media_state.update(data)
        display.async_write_ha_state()
        if coordinator.media_player_entity is not None:
            coordinator.media_player_entity.async_write_ha_state()

    coordinator.register_core_handler("media:state", on_media_state)

    async_add_entities([HubblePageSelectEntity(coordinator, entry), display])


class HubblePageSelectEntity(CoordinatorEntity[HubbleCoordinator], SelectEntity):
    """Select entity for the active Hubble page (options are page slugs)."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_page"

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_active_page"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )

    def _active_page(self) -> dict | None:
        """Return the page dict matching activePage, or None."""
        data = self.coordinator.data
        if not data:
            return None
        active_id = data.get("activePage")
        return next((p for p in data.get("pages", []) if p["id"] == active_id), None)

    @property
    def options(self) -> list[str]:
        """Return all page slugs (guaranteed unique by Hubble API)."""
        if not self.coordinator.data:
            return []
        return [p["slug"] for p in self.coordinator.data.get("pages", [])]

    @property
    def current_option(self) -> str | None:
        """Return the slug of the currently active page."""
        page = self._active_page()
        return page["slug"] if page else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the human-readable name of the active page."""
        page = self._active_page()
        return {"page_name": page["name"]} if page else {}

    async def async_select_option(self, option: str) -> None:
        """Change the active page by slug."""
        if not self.coordinator.data:
            return
        pages = self.coordinator.data.get("pages", [])
        page = next((p for p in pages if p["slug"] == option), None)
        if page is None:
            return
        await self.coordinator.client.async_set_active_page(page["id"])
        await self.coordinator.async_request_refresh()


class HubbleDisplayModeSelect(SelectEntity):
    """Hubble display mode select entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "display_mode"
    _attr_options = DISPLAY_MODES
    _attr_should_poll = False

    def __init__(
        self, coordinator: HubbleCoordinator, entry: HubbleConfigEntry
    ) -> None:
        """Initialise the display mode select entity."""
        self._attr_unique_id = f"{entry.entry_id}_display_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )
        self.coordinator = coordinator
        self.entry = entry

    @property
    def available(self) -> bool:
        """Return True when player state has been fetched."""
        return self.coordinator.media_state is not None

    @property
    def current_option(self) -> str | None:
        """Return the current display mode."""
        if self.coordinator.media_state is None:
            return None
        return self.coordinator.media_state.get("displayMode")

    async def async_select_option(self, option: str) -> None:
        """Change the display mode."""
        try:
            await self.coordinator.client.async_media_set_display(option)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
