"""Hubble media player entity."""

from __future__ import annotations

import logging

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import HubbleError
from .const import DOMAIN
from .coordinator import HubbleConfigEntry

_LOGGER = logging.getLogger(__name__)

_HUBBLE_STATE_MAP: dict[str, MediaPlayerState] = {
    "off": MediaPlayerState.OFF,
    "idle": MediaPlayerState.IDLE,
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
}

_MEDIA_TYPE_MAP: dict[str, str] = {
    MediaType.MUSIC: "audio",
    MediaType.VIDEO: "video",
    MediaType.MOVIE: "video",
    "music": "audio",
    "video": "video",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HubbleConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Hubble media player entity.

    Initial media state is fetched by the select platform (which runs before
    media_player due to HA dependency ordering) and stored on coordinator.media_state.
    If for any reason the select platform has not yet populated it, we fetch here.
    The media:state core handler is also registered by the select platform.
    """
    coordinator = entry.runtime_data

    # Fetch initial media state if not already present (select platform may have
    # already populated coordinator.media_state).
    if coordinator.media_state is None:
        try:
            coordinator.media_state = await coordinator.client.async_media_get_state()
        except HubbleError:
            _LOGGER.warning("Failed to fetch initial Hubble media player state")
            coordinator.media_state = None

    player = HubbleMediaPlayer(coordinator, entry)
    # Store on coordinator so the media:state handler (registered by select platform)
    # can call async_write_ha_state on this entity.
    coordinator.media_player_entity = player
    async_add_entities([player])


class HubbleMediaPlayer(MediaPlayerEntity):
    """Hubble media player entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "media_player"
    _attr_should_poll = False
    _attr_media_image_remotely_accessible = True
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
    )

    def __init__(self, coordinator, entry: HubbleConfigEntry) -> None:
        """Initialise the media player entity."""
        self._attr_unique_id = f"{entry.entry_id}_media_player"
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

    async def async_will_remove_from_hass(self) -> None:
        """Clean up stored reference when entity is removed."""
        if self.coordinator.media_player_entity is self:
            self.coordinator.media_player_entity = None
