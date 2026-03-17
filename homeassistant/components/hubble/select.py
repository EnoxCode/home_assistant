"""Hubble select platform — active page selector."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble select entities from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities([HubblePageSelectEntity(coordinator, entry)])


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
