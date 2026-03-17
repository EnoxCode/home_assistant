"""Tests for Hubble media player and display mode select entities."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.hubble.api import HubbleConnectionError
from homeassistant.components.hubble.const import DOMAIN
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from . import (
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
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    player = hass.states.get("media_player.kitchen_screen_media_player")
    display = hass.states.get("select.kitchen_screen_display_mode")
    assert player is not None
    assert player.state == STATE_UNAVAILABLE
    assert display is not None
    assert display.state == STATE_UNAVAILABLE
