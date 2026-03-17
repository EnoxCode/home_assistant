"""Hubble sensor platform — current page."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_HOST, CONF_PORT
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
    """Set up Hubble sensors from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities([HubbleCurrentPageSensor(coordinator, entry)])


class HubbleCurrentPageSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the currently active Hubble page."""

    _attr_has_entity_name = True
    _attr_translation_key = "current_page"

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_page"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Hubble ({entry.data[CONF_HOST]}:{entry.data[CONF_PORT]})",
            manufacturer="Hubble",
        )

    def _current_page(self) -> dict[str, Any] | None:
        """Return the page dict matching activePage, or None."""
        data = self.coordinator.data
        if not data:
            return None
        active_id = data.get("activePage")
        return next((p for p in data.get("pages", []) if p["id"] == active_id), None)

    @property
    def available(self) -> bool:
        """Return False when coordinator data is missing or page not found."""
        return super().available and self._current_page() is not None

    @property
    def native_value(self) -> str | None:
        """Return the name of the currently active page."""
        page = self._current_page()
        return page["name"] if page else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return slug and id of the active page."""
        page = self._current_page()
        if page is None:
            return {}
        return {"slug": page["slug"], "id": page["id"]}
