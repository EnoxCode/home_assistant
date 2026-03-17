"""Hubble button platform."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HubbleApiClient
from .const import DOMAIN
from .coordinator import HubbleConfigEntry, HubbleCoordinator


@dataclass(frozen=True, kw_only=True)
class HubbleButtonEntityDescription(ButtonEntityDescription):
    """Describes a Hubble button entity."""

    press_fn: Callable[[HubbleApiClient], Coroutine[Any, Any, Any]]


BUTTON_DESCRIPTIONS: tuple[HubbleButtonEntityDescription, ...] = (
    HubbleButtonEntityDescription(
        key="next_page",
        translation_key="next_page",
        press_fn=lambda client: client.async_next_page(),
    ),
    HubbleButtonEntityDescription(
        key="previous_page",
        translation_key="previous_page",
        press_fn=lambda client: client.async_previous_page(),
    ),
    HubbleButtonEntityDescription(
        key="next_widget",
        translation_key="next_widget",
        press_fn=lambda client: client.async_next_widget(),
    ),
    HubbleButtonEntityDescription(
        key="previous_widget",
        translation_key="previous_widget",
        press_fn=lambda client: client.async_previous_widget(),
    ),
    HubbleButtonEntityDescription(
        key="dismiss_all_notifications",
        translation_key="dismiss_all_notifications",
        press_fn=lambda client: client.async_dismiss_all_notifications(),
    ),
    HubbleButtonEntityDescription(
        key="refresh_dashboard",
        translation_key="refresh_dashboard",
        press_fn=lambda client: client.async_refresh_dashboard(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble button entities from a config entry."""
    coordinator: HubbleCoordinator = entry.runtime_data
    async_add_entities(
        HubbleButton(coordinator, entry, description)
        for description in BUTTON_DESCRIPTIONS
    )


class HubbleButton(CoordinatorEntity[HubbleCoordinator], ButtonEntity):
    """A Hubble button entity."""

    _attr_has_entity_name = True
    entity_description: HubbleButtonEntityDescription

    def __init__(
        self,
        coordinator: HubbleCoordinator,
        entry: HubbleConfigEntry,
        description: HubbleButtonEntityDescription,
    ) -> None:
        """Initialise the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        await self.entity_description.press_fn(self.coordinator.client)
        await self.coordinator.async_request_refresh()
