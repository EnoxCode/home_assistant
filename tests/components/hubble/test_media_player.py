"""Tests for Hubble media player and display mode select entities."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import (
    MOCK_COMMAND_EXECUTE_RESULT,
    MOCK_DASHBOARD_STATE,
    MOCK_DISCOVERY,
    MOCK_MEDIA_STATE,
    MOCK_NOTIFY_COUNT,
    MOCK_USER_INPUT,
)

from tests.common import MockConfigEntry


@pytest.fixture
async def setup_media_player(hass: HomeAssistant):
    """Set up Hubble integration with a mocked media player state.

    Returns the config entry. All API calls are mocked; WebSocket is suppressed.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=MOCK_USER_INPUT,
        title="Kitchen Screen",
    )
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            return_value=dict(MOCK_MEDIA_STATE)
        )
        mock_client.async_execute_command = AsyncMock(
            return_value=dict(MOCK_COMMAND_EXECUTE_RESULT)
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock_client


# ── Platform setup ────────────────────────────────────────────────────────────


async def test_media_player_entity_created(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform creates a media_player entity."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state is not None


async def test_display_mode_select_entity_created(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform creates a display_mode select entity alongside the media player."""
    state = hass.states.get("select.kitchen_screen_display_mode")
    assert state is not None


async def test_initial_state_fetched(hass: HomeAssistant, setup_media_player) -> None:
    """async_media_get_state is called once during setup."""
    entry, mock_client = setup_media_player
    mock_client.async_media_get_state.assert_called_once()


async def test_media_state_handler_registered_on_coordinator(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Platform registers a 'media:state' core handler on the coordinator."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    assert "media:state" in coordinator._core_handlers


# ── State mapping ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hubble_state", "expected"),
    [
        ("off", "off"),
        ("idle", "idle"),
        ("playing", "playing"),
        ("paused", "paused"),
        ("buffering", "buffering"),
    ],
)
async def test_state_mapping(
    hass: HomeAssistant,
    setup_media_player,
    hubble_state: str,
    expected: str,
) -> None:
    """Hubble state strings map correctly to HA MediaPlayerState values."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state", {**MOCK_MEDIA_STATE, "state": hubble_state}
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.state == expected


async def test_media_content_type_audio_maps_to_music(
    hass: HomeAssistant, setup_media_player
) -> None:
    """MediaContentType 'audio' maps to MediaType.MUSIC."""
    entry, _ = setup_media_player
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_content_type") == "music"


async def test_media_content_type_video_maps_to_video(
    hass: HomeAssistant, setup_media_player
) -> None:
    """MediaContentType 'video' maps to MediaType.VIDEO."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state", {**MOCK_MEDIA_STATE, "mediaContentType": "video"}
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_content_type") == "video"


async def test_media_title_exposed(hass: HomeAssistant, setup_media_player) -> None:
    """media_title attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_title") == "Bohemian Rhapsody"


async def test_media_artist_exposed(hass: HomeAssistant, setup_media_player) -> None:
    """media_artist attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_artist") == "Queen"


async def test_entity_picture_uses_media_image_url(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_image_url (not entity_picture) carries the artwork URL."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("entity_picture") == "http://nas.local/covers/queen.jpg"


async def test_volume_level_exposed(hass: HomeAssistant, setup_media_player) -> None:
    """volume_level attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("volume_level") == 0.7


async def test_is_volume_muted_exposed(hass: HomeAssistant, setup_media_player) -> None:
    """is_volume_muted attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("is_volume_muted") is False


async def test_extra_state_attributes_display_mode(
    hass: HomeAssistant, setup_media_player
) -> None:
    """display_mode extra attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("display_mode") == "none"


async def test_extra_state_attributes_announcing(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Announcing extra attribute is populated from MOCK_MEDIA_STATE."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("announcing") is False


# ── Position extrapolation ───────────────────────────────────────────────────


async def test_media_position_extrapolated_when_playing(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position adds elapsed time since mediaPositionUpdatedAt when playing."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data

    # Freeze time: 10 seconds after the position timestamp in MOCK_MEDIA_STATE
    # (mediaPositionUpdatedAt = "2026-03-17T10:23:45.123+00:00")
    frozen = datetime.datetime(2026, 3, 17, 10, 23, 55, 123000, tzinfo=datetime.UTC)
    with patch("homeassistant.util.dt.utcnow", return_value=frozen):
        # Trigger a state update so properties are recomputed with the frozen time.
        # hass.states.get() returns already-evaluated attribute values; we must call
        # async_write_ha_state() (via the WS handler) while the patch is active.
        coordinator._handle_ws_event("media:state", dict(MOCK_MEDIA_STATE))
        await hass.async_block_till_done()
        state = hass.states.get("media_player.kitchen_screen_media_player")
        # position=42.0 + 10s elapsed = 52.0
        assert state.attributes.get("media_position") == pytest.approx(52.0, abs=0.1)


async def test_media_position_raw_when_paused(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position returns raw value (no extrapolation) when not playing."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state", {**MOCK_MEDIA_STATE, "state": "paused", "mediaPosition": 42.0}
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_position") == 42.0


async def test_media_position_raw_when_updated_at_unparsable(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position falls back to raw value when timestamp cannot be parsed."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state",
        {
            **MOCK_MEDIA_STATE,
            "state": "playing",
            "mediaPositionUpdatedAt": "not-a-date",
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_position") == 42.0


async def test_media_position_capped_at_duration(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position never exceeds mediaDuration."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data

    # Advance far past the timestamp (elapsed >> duration of 354.0)
    frozen = datetime.datetime(2026, 3, 17, 10, 40, 25, 123000, tzinfo=datetime.UTC)
    with patch("homeassistant.util.dt.utcnow", return_value=frozen):
        coordinator._handle_ws_event("media:state", dict(MOCK_MEDIA_STATE))
        await hass.async_block_till_done()
        state = hass.states.get("media_player.kitchen_screen_media_player")
        # Duration is 354.0 — must be capped
        assert state.attributes.get("media_position") <= 354.0


# ── Source properties ─────────────────────────────────────────────────────────


async def test_source_returns_label_for_active_source(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Source property returns the label matching the active source ID."""
    # MOCK_MEDIA_STATE source="default", sourceList has id="default" label="Default"
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source") == "Default"


async def test_source_returns_raw_id_when_not_in_source_list(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Source falls back to the raw ID when it's not in sourceList."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state",
        {**MOCK_MEDIA_STATE, "source": "unknown-device-id"},
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source") == "unknown-device-id"


async def test_source_returns_none_when_source_is_null(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Source property returns None when Hubble reports source as null."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event("media:state", {**MOCK_MEDIA_STATE, "source": None})
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source") is None


async def test_source_list_returns_labels(
    hass: HomeAssistant, setup_media_player
) -> None:
    """source_list exposes display labels, not device IDs."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source_list") == ["Default", "HDMI Output"]


async def test_entities_unavailable_when_initial_fetch_fails(
    hass: HomeAssistant,
) -> None:
    """Both entities start unavailable when async_media_get_state raises."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            side_effect=HubbleConnectionError("timeout")
        )
        mock_client.async_execute_command = AsyncMock(
            return_value=dict(MOCK_COMMAND_EXECUTE_RESULT)
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    player = hass.states.get("media_player.kitchen_screen_media_player")
    display = hass.states.get("select.kitchen_screen_display_mode")
    assert player is not None
    assert player.state == STATE_UNAVAILABLE
    assert display is not None
    assert display.state == STATE_UNAVAILABLE


# ── Service methods ───────────────────────────────────────────────────────────


async def test_turn_on_calls_screen_on_command(
    hass: HomeAssistant, setup_media_player
) -> None:
    """turn_on executes the screen-on command via the commands API."""
    entry, mock_client = setup_media_player
    mock_client.async_execute_command = AsyncMock(
        return_value={"ok": True, "stdout": "true", "stderr": "", "exitCode": 0}
    )
    await hass.services.async_call(
        "media_player",
        "turn_on",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_execute_command.assert_any_call("screen-on")


async def test_turn_off_calls_screen_off_and_stop(
    hass: HomeAssistant, setup_media_player
) -> None:
    """turn_off executes the screen-off command and stops media playback."""
    entry, mock_client = setup_media_player
    mock_client.async_execute_command = AsyncMock(
        return_value={"ok": True, "stdout": "false", "stderr": "", "exitCode": 0}
    )
    mock_client.async_media_stop = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "turn_off",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_execute_command.assert_any_call("screen-off")
    mock_client.async_media_stop.assert_called_once()


async def test_media_play_calls_resume(hass: HomeAssistant, setup_media_player) -> None:
    """media_play service calls async_media_resume on the client."""
    entry, mock_client = setup_media_player
    mock_client.async_media_resume = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "media_play",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_resume.assert_called_once()


async def test_media_pause_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    """media_pause service calls async_media_pause on the client."""
    entry, mock_client = setup_media_player
    mock_client.async_media_pause = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "media_pause",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_pause.assert_called_once()


async def test_media_stop_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    """media_stop service calls async_media_stop on the client."""
    entry, mock_client = setup_media_player
    mock_client.async_media_stop = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "media_stop",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_stop.assert_called_once()


async def test_volume_set_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    """volume_set service calls async_media_set_volume_level with correct level."""
    entry, mock_client = setup_media_player
    mock_client.async_media_set_volume_level = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.5, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {"entity_id": "media_player.kitchen_screen_media_player", "volume_level": 0.5},
        blocking=True,
    )
    mock_client.async_media_set_volume_level.assert_called_once_with(0.5)


async def test_mute_volume_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    """volume_mute service calls async_media_mute_volume with the mute flag."""
    entry, mock_client = setup_media_player
    mock_client.async_media_mute_volume = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.7, "isVolumeMuted": True}
    )
    await hass.services.async_call(
        "media_player",
        "volume_mute",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "is_volume_muted": True,
        },
        blocking=True,
    )
    mock_client.async_media_mute_volume.assert_called_once_with(True)


async def test_volume_up_calls_step_up(hass: HomeAssistant, setup_media_player) -> None:
    """volume_up service calls async_media_volume_step with 'up'."""
    entry, mock_client = setup_media_player
    mock_client.async_media_volume_step = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.8, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player",
        "volume_up",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_volume_step.assert_called_once_with("up")


async def test_volume_down_calls_step_down(
    hass: HomeAssistant, setup_media_player
) -> None:
    """volume_down service calls async_media_volume_step with 'down'."""
    entry, mock_client = setup_media_player
    mock_client.async_media_volume_step = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.6, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player",
        "volume_down",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_volume_step.assert_called_once_with("down")


async def test_service_error_raises_home_assistant_error(
    hass: HomeAssistant, setup_media_player
) -> None:
    """HubbleError from any service call surfaces as HomeAssistantError."""
    entry, mock_client = setup_media_player
    mock_client.async_execute_command = AsyncMock(
        side_effect=HubbleConnectionError("timeout")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player",
            "turn_on",
            {"entity_id": "media_player.kitchen_screen_media_player"},
            blocking=True,
        )


# ── play_media ────────────────────────────────────────────────────────────────


async def test_play_media_maps_music_content_type(
    hass: HomeAssistant, setup_media_player
) -> None:
    """MediaType.MUSIC maps to contentType 'audio' in the POST body."""
    entry, mock_client = setup_media_player
    mock_client.async_media_play = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "media_content_id": "http://nas.local/track.mp3",
            "media_content_type": "music",
        },
        blocking=True,
    )
    mock_client.async_media_play.assert_called_once()
    call_kwargs = mock_client.async_media_play.call_args[1]
    assert call_kwargs["url"] == "http://nas.local/track.mp3"
    assert call_kwargs["content_type"] == "audio"
    assert call_kwargs["announce"] is False


async def test_play_media_with_announce_true(
    hass: HomeAssistant, setup_media_player
) -> None:
    """announce=True is forwarded to async_media_play for TTS overlay support."""
    entry, mock_client = setup_media_player
    mock_client.async_media_play = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "media_content_id": "http://ha.local/tts.mp3",
            "media_content_type": "music",
            "announce": True,
        },
        blocking=True,
    )
    call_kwargs = mock_client.async_media_play.call_args[1]
    assert call_kwargs["announce"] is True


async def test_play_media_extra_fields_forwarded(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Extra dict fields (title, artist, imageUrl, volume, displayMode) are forwarded."""
    entry, mock_client = setup_media_player
    mock_client.async_media_play = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "media_content_id": "http://nas.local/track.mp3",
            "media_content_type": "music",
            "extra": {
                "title": "Bohemian Rhapsody",
                "artist": "Queen",
                "imageUrl": "http://nas.local/cover.jpg",
                "volume": 0.8,
                "displayMode": "none",
            },
        },
        blocking=True,
    )
    call_kwargs = mock_client.async_media_play.call_args[1]
    assert call_kwargs["title"] == "Bohemian Rhapsody"
    assert call_kwargs["artist"] == "Queen"
    assert call_kwargs["image_url"] == "http://nas.local/cover.jpg"
    assert call_kwargs["volume"] == 0.8
    assert call_kwargs["display_mode"] == "none"


async def test_play_media_unknown_content_type_sends_none(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Unknown media_content_type sends content_type=None (API auto-detects)."""
    entry, mock_client = setup_media_player
    mock_client.async_media_play = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "media_content_id": "http://nas.local/file.mp3",
            "media_content_type": "podcast",
        },
        blocking=True,
    )
    call_kwargs = mock_client.async_media_play.call_args[1]
    assert call_kwargs["content_type"] is None


# ── select_source ─────────────────────────────────────────────────────────────


async def test_select_source_maps_label_to_id(
    hass: HomeAssistant, setup_media_player
) -> None:
    """select_source maps the display label to the device ID before calling API."""
    entry, mock_client = setup_media_player
    mock_client.async_media_set_source = AsyncMock(
        return_value={"success": True, "source": "hdmi"}
    )
    await hass.services.async_call(
        "media_player",
        "select_source",
        {
            "entity_id": "media_player.kitchen_screen_media_player",
            "source": "HDMI Output",
        },
        blocking=True,
    )
    mock_client.async_media_set_source.assert_called_once_with("hdmi")


async def test_select_source_unknown_label_passes_through(
    hass: HomeAssistant, setup_media_player
) -> None:
    """Unknown label is passed as-is; API returns 400 → HomeAssistantError."""
    entry, mock_client = setup_media_player
    mock_client.async_media_set_source = AsyncMock(
        side_effect=HubbleConnectionError("Source not available")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player",
            "select_source",
            {
                "entity_id": "media_player.kitchen_screen_media_player",
                "source": "Bluetooth Headphones",
            },
            blocking=True,
        )
    # Unknown label passed as-is to the API
    mock_client.async_media_set_source.assert_called_once_with("Bluetooth Headphones")


# ── Display mode select entity ────────────────────────────────────────────────


async def test_display_select_current_option(
    hass: HomeAssistant, setup_media_player
) -> None:
    """current_option reflects displayMode from player state."""
    state = hass.states.get("select.kitchen_screen_display_mode")
    assert state.state == "none"  # MOCK_MEDIA_STATE displayMode is "none"


async def test_display_select_option_calls_api(
    hass: HomeAssistant, setup_media_player
) -> None:
    """select_option service calls async_media_set_display with the chosen mode."""
    entry, mock_client = setup_media_player
    mock_client.async_media_set_display = AsyncMock(
        return_value={"success": True, "displayMode": "fullscreen"}
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": "select.kitchen_screen_display_mode",
            "option": "fullscreen",
        },
        blocking=True,
    )
    mock_client.async_media_set_display.assert_called_once_with("fullscreen")


async def test_display_select_error_raises_home_assistant_error(
    hass: HomeAssistant, setup_media_player
) -> None:
    """HubbleError from display mode change surfaces as HomeAssistantError."""
    entry, mock_client = setup_media_player
    mock_client.async_media_set_display = AsyncMock(
        side_effect=HubbleConnectionError("bad mode")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": "select.kitchen_screen_display_mode",
                "option": "fullscreen",
            },
            blocking=True,
        )


# ── WS event flow: shared state ───────────────────────────────────────────────


async def test_media_state_ws_event_updates_both_entities(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media:state WS event updates both player and display select."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state",
        {**MOCK_MEDIA_STATE, "state": "paused", "displayMode": "fullscreen"},
    )
    await hass.async_block_till_done()

    player = hass.states.get("media_player.kitchen_screen_media_player")
    display = hass.states.get("select.kitchen_screen_display_mode")
    assert player.state == "paused"
    assert display.state == "fullscreen"


async def test_both_entities_share_dict_after_ws_recovery(
    hass: HomeAssistant,
) -> None:
    """After recovery from None, both entities share the same coordinator.media_state dict."""
    entry = MockConfigEntry(domain=DOMAIN, data=MOCK_USER_INPUT, title="Kitchen Screen")
    entry.add_to_hass(hass)

    with (
        patch("homeassistant.components.hubble.HubbleApiClient") as mock_cls,
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_start_websocket"
        ),
        patch(
            "homeassistant.components.hubble.coordinator.HubbleCoordinator.async_stop_websocket"
        ),
    ):
        mock_client = mock_cls.return_value
        mock_client.async_get_state = AsyncMock(return_value=MOCK_DASHBOARD_STATE)
        mock_client.async_get_notify_count = AsyncMock(return_value=MOCK_NOTIFY_COUNT)
        mock_client.async_discover = AsyncMock(return_value=MOCK_DISCOVERY)
        mock_client.async_get_connector_state = AsyncMock(return_value={})
        mock_client.async_media_get_state = AsyncMock(
            side_effect=HubbleConnectionError("timeout")
        )
        mock_client.async_execute_command = AsyncMock(
            return_value=dict(MOCK_COMMAND_EXECUTE_RESULT)
        )
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = entry.runtime_data
        # Simulate first WS event arriving after failed initial fetch
        coordinator._handle_ws_event("media:state", dict(MOCK_MEDIA_STATE))
        await hass.async_block_till_done()

        player = hass.states.get("media_player.kitchen_screen_media_player")
        display = hass.states.get("select.kitchen_screen_display_mode")
        assert player.state == "playing"
        assert display.state == "none"
