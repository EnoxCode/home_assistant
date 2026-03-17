"""Hubble sensor platform."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
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
    """Set up Hubble sensors from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities([
        HubbleCurrentPageSensor(coordinator, entry),
        HubbleModuleCountSensor(coordinator, entry),
        HubbleNotificationCountSensor(coordinator, entry),
    ])


def _device_info(entry: HubbleConfigEntry) -> DeviceInfo:
    """Return shared DeviceInfo for all Hubble entities."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "Hubble"),
        manufacturer="Hubble",
    )


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
        self._attr_device_info = _device_info(entry)

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


class HubbleModuleCountSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the number of installed Hubble modules."""

    _attr_has_entity_name = True
    _attr_translation_key = "module_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_module_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int:
        """Return the number of installed modules."""
        if not (data := self.coordinator.data):
            return 0
        return len(data.get("modules", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the names of all installed modules."""
        if not (data := self.coordinator.data):
            return {}
        modules = data.get("modules", [])
        return {"modules": [m.get("name") for m in modules if m.get("name")]}


class HubbleNotificationCountSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor reporting the number of active dashboard notifications."""

    _attr_has_entity_name = True
    _attr_translation_key = "notification_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_notification_count"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> int | None:
        """Return the number of active notifications."""
        if not (data := self.coordinator.data):
            return None
        return data.get("notificationCount")
