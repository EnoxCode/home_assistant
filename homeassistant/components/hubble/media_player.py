"""Hubble media player entity."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    ATTR_MEDIA_EXTRA,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components import media_source
from homeassistant.components.media_player.browse_media import (
    async_process_play_media_url,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import homeassistant.util.dt as dt_util

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

    @property
    def state(self) -> MediaPlayerState | None:
        """Return current playback state."""
        if self.coordinator.media_state is None:
            return None
        return _HUBBLE_STATE_MAP.get(self.coordinator.media_state.get("state", ""))

    @property
    def media_content_id(self) -> str | None:
        """Return media content ID (URL or identifier)."""
        return (self.coordinator.media_state or {}).get("mediaContentId")

    @property
    def media_content_type(self) -> MediaType | None:
        """Return mapped HA media content type."""
        raw = (self.coordinator.media_state or {}).get("mediaContentType")
        if raw == "audio":
            return MediaType.MUSIC
        if raw == "video":
            return MediaType.VIDEO
        return None

    @property
    def media_title(self) -> str | None:
        """Return track/media title."""
        return (self.coordinator.media_state or {}).get("mediaTitle")

    @property
    def media_artist(self) -> str | None:
        """Return artist name."""
        return (self.coordinator.media_state or {}).get("mediaArtist")

    @property
    def media_image_url(self) -> str | None:
        """Return URL for album/media artwork."""
        return (self.coordinator.media_state or {}).get("mediaImageUrl")

    @property
    def media_duration(self) -> int | None:
        """Return total media duration in seconds."""
        return (self.coordinator.media_state or {}).get("mediaDuration")

    @property
    def volume_level(self) -> float | None:
        """Return volume level (0.0–1.0)."""
        return (self.coordinator.media_state or {}).get("volumeLevel")

    @property
    def is_volume_muted(self) -> bool | None:
        """Return True if volume is muted."""
        return (self.coordinator.media_state or {}).get("isVolumeMuted")

    @property
    def media_position(self) -> int | None:
        """Return extrapolated position when playing, raw position otherwise."""
        if self.coordinator.media_state is None:
            return None
        pos = self.coordinator.media_state.get("mediaPosition")
        updated_at_str = self.coordinator.media_state.get("mediaPositionUpdatedAt")
        if (
            self.coordinator.media_state.get("state") != "playing"
            or pos is None
            or updated_at_str is None
        ):
            return pos
        updated_at = dt_util.parse_datetime(updated_at_str)
        if updated_at is None:
            return pos
        elapsed = (dt_util.utcnow() - updated_at).total_seconds()
        duration = self.coordinator.media_state.get("mediaDuration") or float("inf")
        return min(pos + elapsed, duration)

    @property
    def media_position_updated_at(self):
        """Return the timestamp when media position was last updated."""
        if self.coordinator.media_state is None:
            return None
        raw = self.coordinator.media_state.get("mediaPositionUpdatedAt")
        if raw is None:
            return None
        return dt_util.parse_datetime(raw)

    @property
    def source(self) -> str | None:
        """Return the label for the active source, or the raw ID if not in list."""
        if self.coordinator.media_state is None:
            return None
        active_id = self.coordinator.media_state.get("source")
        if active_id is None:
            return None
        source_list = self.coordinator.media_state.get("sourceList", [])
        return next(
            (s["label"] for s in source_list if s["id"] == active_id),
            active_id,  # fallback: return raw ID if not found in list
        )

    @property
    def source_list(self) -> list[str] | None:
        """Return list of source labels."""
        if self.coordinator.media_state is None:
            return None
        return [s["label"] for s in self.coordinator.media_state.get("sourceList", [])]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return Hubble-specific attributes."""
        if self.coordinator.media_state is None:
            return {}
        return {
            "display_mode": self.coordinator.media_state.get("displayMode"),
            "announcing": self.coordinator.media_state.get("announcing"),
        }

    async def async_turn_on(self) -> None:
        """Turn on the media player."""
        try:
            await self.coordinator.client.async_media_turn_on()
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_off(self) -> None:
        """Turn off the media player."""
        try:
            await self.coordinator.client.async_media_turn_off()
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_play(self) -> None:
        """Send play command (resume)."""
        try:
            await self.coordinator.client.async_media_resume()
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_pause(self) -> None:
        """Send pause command."""
        try:
            await self.coordinator.client.async_media_pause()
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_media_stop(self) -> None:
        """Send stop command."""
        try:
            await self.coordinator.client.async_media_stop()
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        try:
            await self.coordinator.client.async_media_set_volume_level(volume)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute (true) or unmute (false) media player."""
        try:
            await self.coordinator.client.async_media_mute_volume(mute)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        try:
            await self.coordinator.client.async_media_volume_step("up")
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        try:
            await self.coordinator.client.async_media_volume_step("down")
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media."""
        announce: bool = kwargs.get("announce", False)
        extra: dict[str, Any] = kwargs.get(ATTR_MEDIA_EXTRA, {})
        content_type = _MEDIA_TYPE_MAP.get(str(media_type))

        if media_source.is_media_source_id(media_id):
            sourced = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = async_process_play_media_url(self.hass, sourced.url)

        try:
            await self.coordinator.client.async_media_play(
                url=media_id,
                content_type=content_type,
                title=extra.get("title"),
                artist=extra.get("artist"),
                image_url=extra.get("imageUrl"),
                volume=extra.get("volume"),
                display_mode=extra.get("displayMode"),
                announce=announce,
            )
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        source_list = (self.coordinator.media_state or {}).get("sourceList", [])
        source_id = next(
            (s["id"] for s in source_list if s["label"] == source),
            source,  # fallback: pass raw string; API returns 400 → HomeAssistantError
        )
        try:
            await self.coordinator.client.async_media_set_source(source_id)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_will_remove_from_hass(self) -> None:
        """Clean up stored reference when entity is removed."""
        if self.coordinator.media_player_entity is self:
            self.coordinator.media_player_entity = None
