"""Hubble sensor platform."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import HubbleAuthError, HubbleConnectionError
from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator

_TIMER_MODULE = "hubble-timer"
_TIMER_TOPICS: tuple[str, ...] = (
    "timer:started",
    "timer:paused",
    "timer:resumed",
    "timer:finished",
    "timer:reset",
)
# Priority order for initialising sensor state from connector-state data.
# Higher priority = checked first. The order reflects "most definitive current
# state": paused > finished > reset > started > resumed.
_INIT_PRIORITY: tuple[str, ...] = (
    "timer:paused",
    "timer:finished",
    "timer:reset",
    "timer:started",
    "timer:resumed",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble sensors from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        HubbleCurrentPageSensor(coordinator, entry),
        HubbleModuleCountSensor(coordinator, entry),
        HubbleNotificationCountSensor(coordinator, entry),
    ]

    if coordinator.is_module_discovered(_TIMER_MODULE):
        timer_module = next(
            m
            for m in coordinator.discovery.get("modules", [])
            if m["module"] == _TIMER_MODULE
        )
        timer_sensors: dict[str, HubbleTimerSensor] = {
            inst["config"]["slug"]: HubbleTimerSensor(
                coordinator, entry, inst["config"]["slug"]
            )
            for inst in timer_module.get("instances", [])
        }
        entities.extend(timer_sensors.values())

        # Fetch connector state for best-effort initial sensor values.
        try:
            connector_state = await coordinator.client.async_get_connector_state(
                _TIMER_MODULE
            )
        except (HubbleAuthError, HubbleConnectionError):
            connector_state = {}

        # Initialise each sensor from the highest-priority topic whose payload
        # matches the sensor's slug.
        for sensor in timer_sensors.values():
            for topic in _INIT_PRIORITY:
                payload = connector_state.get(topic)
                if payload and payload.get("slug") == sensor.slug:
                    sensor.apply_topic(topic, payload)
                    break

        # Register one WS handler per topic; each dispatches to the right sensor
        # by slug from the closure over timer_sensors.
        for topic in _TIMER_TOPICS:

            def _make_handler(t: str) -> Callable[[dict[str, Any]], None]:
                def _handler(data: dict[str, Any]) -> None:
                    s = timer_sensors.get(data.get("slug", ""))
                    if s:
                        s.handle_event(t, data)

                return _handler

            coordinator.register_module_handler(
                _TIMER_MODULE, topic, _make_handler(topic)
            )

        coordinator.add_pending_module_subscription(_TIMER_MODULE)

    async_add_entities(entities)


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
        """Return the number of installed modules from discovery data."""
        return len(self.coordinator.discovery.get("modules", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the names of all installed modules from discovery data."""
        modules = self.coordinator.discovery.get("modules", [])
        return {"modules": [m["module"] for m in modules]}


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


class HubbleTimerSensor(CoordinatorEntity[HubbleCoordinator], SensorEntity):
    """Sensor representing one Hubble timer widget instance.

    State: idle | active | paused | finished.
    Updated live from module:data WS events; initialised from connector-state API.
    Named by slug so the entity ID is sensor.{device}_{slug} (hyphens → underscores).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer"

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
        slug: str,
    ) -> None:
        """Initialise the timer sensor."""
        super().__init__(coordinator)
        self._slug = slug
        self._attr_name = slug  # e.g. "timer-1" → sensor.kitchen_screen_timer_1
        self._attr_unique_id = f"{entry.entry_id}_timer_{slug}"
        self._attr_device_info = _device_info(entry)
        # Internal timer state — written by apply_topic / handle_event.
        self._state: str = "idle"
        self._mode: str | None = None
        self._label: str | None = None
        self._duration: float | None = None
        self._finishes_at: str | None = None
        self._elapsed_seconds: float | None = None

    @property
    def slug(self) -> str:
        """Return the timer slug."""
        return self._slug

    @property
    def available(self) -> bool:
        """Return True — timer state is maintained locally via WS events."""
        return True

    @property
    def native_value(self) -> str:
        """Return the timer state."""
        return self._state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return timer attributes."""
        attrs: dict[str, Any] = {"slug": self._slug}
        if self._mode is not None:
            attrs["mode"] = self._mode
        if self._label is not None:
            attrs["label"] = self._label
        if self._duration is not None:
            attrs["duration"] = self._duration
        if self._finishes_at is not None:
            attrs["finishes_at"] = self._finishes_at
        if self._elapsed_seconds is not None:
            attrs["elapsed_seconds"] = self._elapsed_seconds
        return attrs

    def handle_event(self, topic: str, data: dict[str, Any]) -> None:
        """Apply a WS timer event and push the new state to HA."""
        self.apply_topic(topic, data)
        self.async_write_ha_state()

    def apply_topic(self, topic: str, data: dict[str, Any]) -> None:
        """Apply a topic payload to internal state (no HA state write).

        Called both from handle_event (WS) and from async_setup_entry
        (connector-state initialisation).
        """
        match topic:
            case "timer:started":
                self._state = "active"
                self._mode = data.get("mode")
                self._label = data.get("label")
                self._duration = data.get("duration")
                self._elapsed_seconds = 0.0
                if self._duration is not None:
                    self._finishes_at = (
                        dt_util.utcnow() + timedelta(seconds=self._duration)
                    ).isoformat()
                else:
                    self._finishes_at = None
            case "timer:paused":
                self._state = "paused"
                self._elapsed_seconds = data.get("elapsed")
                self._finishes_at = None
            case "timer:resumed":
                self._state = "active"
                self._elapsed_seconds = data.get("elapsed")
                if self._duration is not None and self._elapsed_seconds is not None:
                    remaining = self._duration - self._elapsed_seconds
                    self._finishes_at = (
                        dt_util.utcnow() + timedelta(seconds=remaining)
                    ).isoformat()
                else:
                    self._finishes_at = None
            case "timer:finished":
                self._state = "finished"
                self._finishes_at = None
            case "timer:reset":
                self._state = "idle"
                self._mode = None
                self._label = None
                self._duration = None
                self._finishes_at = None
                self._elapsed_seconds = None
