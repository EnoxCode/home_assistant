# Hubble Integration: Media Player

**Date:** 2026-03-17
**Branch:** hubble-integration
**Status:** Draft

---

## Overview

Add a `media_player` entity to the Hubble HA integration, exposing Hubble's full media playback capabilities. A companion `HubbleDisplayModeSelect` select entity (defined in `media_player.py`) controls the video overlay position independently. State is driven by `media:state` WebSocket push events; REST endpoints handle all commands.

The media player is a core Hubble feature — always present, no discovery guard needed.

---

## 1. Files

### New

| File | Contents |
|---|---|
| `homeassistant/components/hubble/media_player.py` | `HubbleMediaPlayer`, `HubbleDisplayModeSelect`, platform `async_setup_entry` |
| `tests/components/hubble/test_media_player.py` | All media player and display mode select tests |

### Changed

| File | Change |
|---|---|
| `api.py` | Add 11 media player API methods |
| `coordinator.py` | Add `_core_handlers`, `register_core_handler()`, `unregister_core_handler()`, extend `_handle_ws_event` |
| `websocket.py` | Add `"media:state"` to `_DEFAULT_EVENTS` |
| `__init__.py` | Add `Platform.MEDIA_PLAYER` to `PLATFORMS` |
| `strings.json` / `translations/en.json` | Add entity strings for both entities |

---

## 2. Coordinator Extension

Three additions to `coordinator.py`:

```python
# In __init__:
self._core_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}

def register_core_handler(
    self,
    event: str,
    handler: Callable[[dict[str, Any]], None],
) -> None:
    """Register a callback for a named core WebSocket event."""
    self._core_handlers[event] = handler

def unregister_core_handler(self, event: str) -> None:
    """Remove a previously registered core handler. No-op if not registered."""
    self._core_handlers.pop(event, None)
```

`_handle_ws_event` gains a new branch **before** the existing `match` block. If the event name is in `_core_handlers`, call the handler and return. Existing `page:changed` / `notification` handling is unchanged.

```python
def _handle_ws_event(self, event: str, data: dict[str, Any]) -> None:
    if event == "module:data":
        # ... existing module routing unchanged
        return

    # Core handler registry (e.g. media player)
    handler = self._core_handlers.get(event)
    if handler:
        handler(data)
        return

    # Existing dashboard event match block
    current = dict(self.data) if self.data else {}
    match event:
        case "page:changed": ...
        case "notification": ...
        ...
```

---

## 3. WebSocket Subscription

`_DEFAULT_EVENTS` in `websocket.py` gains `"media:state"`:

```python
_DEFAULT_EVENTS: frozenset[str] = frozenset({
    "page:changed",
    "notification",
    "notification:dismissed",
    "media:state",
})
```

`media:state` fires on every REST command and on renderer position reports (~1 s during playback). It carries the full `MediaPlayerState` object including `announcing`, so no separate `media:announce` or `screen:changed` subscription is needed.

---

## 4. API Methods (`api.py`)

Eleven new methods on `HubbleApiClient`. `async_media_get_state` uses `self._session.get(url)` directly **without** `headers=self._headers` — this endpoint does not require authentication. All POST methods use the existing `_async_post` helper.

```python
async def async_media_get_state(self) -> dict[str, Any]:
    """GET /api/media-player/state — no auth header sent.

    This endpoint does not require authentication. A 401 response means the
    server unexpectedly requires auth and is treated as a connection error
    (not an auth error — raising HubbleAuthError would incorrectly trigger
    a re-auth flow for an API key that was never sent).
    """
    url = f"{self._base_url}/api/media-player/state"
    try:
        async with self._session.get(url) as response:
            response.raise_for_status()
            return await response.json()
    except HubbleError:
        raise
    except aiohttp.ClientError as err:
        raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

async def async_media_play(
    self,
    url: str,
    *,
    content_type: str | None = None,
    display_mode: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    image_url: str | None = None,
    volume: float | None = None,
    announce: bool = False,
) -> dict[str, Any]:
    """POST /api/media-player/play.

    Builds the body from non-None optional fields plus announce (always sent).
    """

async def async_media_resume(self) -> dict[str, Any]:
    """POST /api/media-player/resume."""

async def async_media_pause(self) -> dict[str, Any]:
    """POST /api/media-player/pause."""

async def async_media_stop(self) -> dict[str, Any]:
    """POST /api/media-player/stop."""

async def async_media_set_volume_level(self, level: float) -> dict[str, Any]:
    """POST /api/media-player/volume with {"level": level}."""

async def async_media_mute_volume(self, mute: bool) -> dict[str, Any]:
    """POST /api/media-player/volume with {"mute": mute}."""

async def async_media_volume_step(self, direction: Literal["up", "down"]) -> dict[str, Any]:
    """POST /api/media-player/volume with {"step": direction}."""

async def async_media_set_display(self, mode: str) -> dict[str, Any]:
    """POST /api/media-player/display with {"mode": mode}."""

async def async_media_set_source(self, source_id: str) -> dict[str, Any]:
    """POST /api/media-player/source with {"source": source_id}."""

async def async_media_turn_on(self) -> dict[str, Any]:
    """POST /api/media-player/turn-on."""

async def async_media_turn_off(self) -> dict[str, Any]:
    """POST /api/media-player/turn-off."""
```

`async_media_play` builds the POST body by including only non-`None` optional fields plus `announce` (always included, defaults `False`).

---

## 5. Platform Setup

`media_player.py::async_setup_entry` owns shared state and WS handler registration:

```python
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data

    # Best-effort initial state fetch. On failure, entities start unavailable
    # and become available on the first media:state WS event.
    try:
        initial_state: dict[str, Any] | None = (
            await coordinator.client.async_media_get_state()
        )
    except HubbleError:
        _LOGGER.warning("Failed to fetch initial media player state")
        initial_state = None

    player = HubbleMediaPlayer(coordinator, entry)
    display = HubbleDisplayModeSelect(coordinator, entry)
    player._player_state = initial_state
    display._player_state = initial_state  # same dict reference when not None

    async_add_entities([player, display])

    def on_media_state(data: dict[str, Any]) -> None:
        if player._player_state is None:
            player._player_state = data.copy()
            display._player_state = player._player_state
        else:
            player._player_state.update(data)
            # display shares the same dict — no reassignment needed
        player.async_write_ha_state()
        display.async_write_ha_state()

    coordinator.register_core_handler("media:state", on_media_state)
```

**Why shared dict:** both entities read from the same mutable `_player_state` object. `on_media_state` calls `.update()` in-place so both entities always see the same data without extra copies or synchronisation.

**Handler timing:** `async_forward_entry_setups` runs before `async_start_websocket` in `__init__.py`, so the handler is registered before any WS events can arrive.

---

## 6. `HubbleMediaPlayer`

```python
class HubbleMediaPlayer(MediaPlayerEntity):
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

    def __init__(self, coordinator, entry) -> None:
        self._player_state: dict[str, Any] | None = None
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )
        self.coordinator = coordinator
        self.entry = entry
```

`available` returns `self._player_state is not None`.

`async_will_remove_from_hass` removes the handler via the public API: `self.coordinator.unregister_core_handler("media:state")`.

### 6.1 State mapping

```python
_HUBBLE_STATE_MAP = {
    "off":       MediaPlayerState.OFF,
    "idle":      MediaPlayerState.IDLE,
    "playing":   MediaPlayerState.PLAYING,
    "paused":    MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
}
```

### 6.2 Properties

| HA property | Source field | Notes |
|---|---|---|
| `state` | `state` | Map via `_HUBBLE_STATE_MAP`; `None` if key absent |
| `media_content_id` | `mediaContentId` | |
| `media_content_type` | `mediaContentType` | `"audio"` → `MediaType.MUSIC`, `"video"` → `MediaType.VIDEO` |
| `media_title` | `mediaTitle` | |
| `media_artist` | `mediaArtist` | |
| `media_image_url` | `mediaImageUrl` | Standard `MediaPlayerEntity` artwork property (not `entity_picture`) |
| `media_duration` | `mediaDuration` | |
| `media_position` | Extrapolated (§6.3) | |
| `media_position_updated_at` | `mediaPositionUpdatedAt` | Parsed as `datetime` with UTC timezone |
| `volume_level` | `volumeLevel` | |
| `is_volume_muted` | `isVolumeMuted` | |
| `source` | `source` + `sourceList` | Map active ID → label; `None` if `source` field is `null`; fall back to raw ID if ID not found in `sourceList` |
| `source_list` | `sourceList` | `[s["label"] for s in sourceList]` |
| `extra_state_attributes` | `displayMode`, `announcing` | `{"display_mode": ..., "announcing": ...}` |

**`source` property fallback:** if `_player_state["source"]` is a non-null device ID that is not present in `sourceList`, return the raw ID string rather than `None`. This handles stale or unexpected state gracefully.

### 6.3 Position extrapolation

```python
@property
def media_position(self) -> float | None:
    if self._player_state is None:
        return None
    pos = self._player_state.get("mediaPosition")
    updated_at_str = self._player_state.get("mediaPositionUpdatedAt")
    if self._player_state.get("state") != "playing" or pos is None or updated_at_str is None:
        return pos
    updated_at = dt_util.parse_datetime(updated_at_str)
    if updated_at is None:
        return pos
    elapsed = (dt_util.utcnow() - updated_at).total_seconds()
    duration = self._player_state.get("mediaDuration") or float("inf")
    return min(pos + elapsed, duration)
```

`media_position_updated_at` returns `dt_util.parse_datetime(updated_at_str)` (from `homeassistant.util.dt`). This safely handles timezone-naive and timezone-aware ISO 8601 strings and always returns a UTC-aware `datetime` or `None`. Using `dt_util` instead of `datetime.fromisoformat` avoids `TypeError` when the API returns strings without a timezone suffix.

### 6.4 Service methods

| HA service | Entity method | API call |
|---|---|---|
| `turn_on` | `async_turn_on` | `async_media_turn_on()` |
| `turn_off` | `async_turn_off` | `async_media_turn_off()` |
| `media_play` | `async_media_play` | `async_media_resume()` |
| `media_pause` | `async_media_pause` | `async_media_pause()` |
| `media_stop` | `async_media_stop` | `async_media_stop()` |
| `play_media` | `async_play_media` | `async_media_play(url, ...)` |
| `volume_set` | `async_set_volume_level` | `async_media_set_volume_level(volume)` |
| `volume_mute` | `async_mute_volume` | `async_media_mute_volume(mute)` |
| `volume_up` | `async_volume_up` | `async_media_volume_step("up")` |
| `volume_down` | `async_volume_down` | `async_media_volume_step("down")` |
| `select_source` | `async_select_source` | `async_media_set_source(id)` |

All service methods wrap `HubbleError` → `HomeAssistantError`.

**`async_play_media`:**

```python
async def async_play_media(
    self, media_type: MediaType | str, media_id: str, **kwargs: Any
) -> None:
    announce: bool = kwargs.get("announce", False)
    extra: dict = kwargs.get(ATTR_MEDIA_EXTRA, {})
    content_type = _map_media_type(media_type)  # MediaType.MUSIC → "audio", VIDEO → "video", else None
    try:
        await self.coordinator.client.async_media_play(
            url=media_id,
            content_type=content_type,
            title=extra.get("title"),
            artist=extra.get("artist"),
            image_url=extra.get("imageUrl"),
            volume=extra.get("volume"),
            display_mode=extra.get("displayMode"),  # validated by API; invalid value returns 400 → HomeAssistantError
            announce=announce,
        )
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err
```

`MEDIA_ANNOUNCE` declared on the entity causes HA's TTS pipeline to pass `announce=True` in kwargs when `tts.cloud_say` is called with `announce: true`. No client-side validation of `displayMode` — the API returns 400 for invalid values which surfaces as `HomeAssistantError`.

**`async_select_source`:**

```python
async def async_select_source(self, source: str) -> None:
    source_list = (self._player_state or {}).get("sourceList", [])
    source_id = next(
        (s["id"] for s in source_list if s["label"] == source),
        source,  # label not found: pass through as-is; API returns 400 → HomeAssistantError
    )
    try:
        await self.coordinator.client.async_media_set_source(source_id)
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err
```

---

## 7. `HubbleDisplayModeSelect`

Defined in `media_player.py` alongside `HubbleMediaPlayer`. Registered via the `media_player` platform's `async_add_entities`, so HA resolves its translation strings under `entity.media_player.display_mode` (not `entity.select.display_mode`).

```python
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

class HubbleDisplayModeSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "display_mode"
    _attr_options = DISPLAY_MODES

    def __init__(self, coordinator, entry) -> None:
        self._player_state: dict[str, Any] | None = None
        self._attr_unique_id = f"{entry.entry_id}_display_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, "Hubble"),
            manufacturer="Hubble",
        )
        self.coordinator = coordinator
```

`current_option` returns `self._player_state.get("displayMode") if self._player_state else None`.

`available` returns `self._player_state is not None`.

`async_select_option` calls `async_media_set_display(option)`, wrapping `HubbleError` → `HomeAssistantError`.

---

## 8. Error Handling

| Condition | Behaviour |
|---|---|
| Initial state fetch fails (`HubbleError`) | Log warning; `_player_state = None`; both entities unavailable until first `media:state` WS event |
| Any REST command fails (`HubbleError`) | Raise `HomeAssistantError` — surfaces in HA UI |
| `select_source` label not found in list | Pass raw string to API; API returns 400 → `HomeAssistantError` |
| `source` property: active ID not in `sourceList` | Return raw ID string (not `None`) |
| `async_play_media` with invalid `displayMode` in `extra` | No client-side validation; API returns 400 → `HomeAssistantError` |
| `media:state` missing a field | All properties use `.get()` with `None` default — no crash |
| WS handler called when `_player_state` is `None` | Handler creates new dict from data and assigns to both entities |

---

## 9. Strings

`strings.json` and `translations/en.json` gain entries. `HubbleDisplayModeSelect` is registered via the `media_player` platform so its translation lives under `entity.media_player` (not `entity.select`):

```json
{
  "entity": {
    "media_player": {
      "media_player": { "name": "Media Player" },
      "display_mode": {
        "name": "Display Mode",
        "state": {
          "fullscreen":   "Fullscreen",
          "half-top":     "Half top",
          "half-bottom":  "Half bottom",
          "quarter-tl":   "Quarter top-left",
          "quarter-tr":   "Quarter top-right",
          "quarter-bl":   "Quarter bottom-left",
          "quarter-br":   "Quarter bottom-right",
          "none":         "None"
        }
      }
    }
  }
}
```

---

## 10. Testing (`test_media_player.py`)

### Setup
- Platform creates `HubbleMediaPlayer` and `HubbleDisplayModeSelect`
- Initial state fetched and assigned to both entities (same dict reference)
- `"media:state"` core handler registered on coordinator
- Both entities unavailable when initial fetch raises `HubbleConnectionError`
- Both entities become available on first `media:state` WS event when initial fetch failed
- After recovery from `None`, `player._player_state is display._player_state` (same dict reference restored)
- Both entities are associated with the Hubble device (share `device_info` identifiers)

### State & properties
- Each Hubble state string maps to correct `MediaPlayerState`
- `"audio"` → `MediaType.MUSIC`, `"video"` → `MediaType.VIDEO`, unknown → `None`
- `source` returns label when ID found in `sourceList`
- `source` returns raw ID string when ID is not in `sourceList`
- `source` returns `None` when `_player_state["source"]` is `null`
- `source_list` returns list of labels
- `media_image_url` returns `mediaImageUrl` (not `entity_picture`)
- Position extrapolated from `mediaPosition + elapsed` when `state == "playing"`
- Position returns raw `mediaPosition` when paused / idle / stopped
- Position returns raw `mediaPosition` when `mediaPositionUpdatedAt` is unparsable (returns `None` from `dt_util.parse_datetime`)
- `extra_state_attributes` contains `display_mode` and `announcing`

### WS events
- `media:state` event updates `_player_state` and triggers `async_write_ha_state` on both entities
- `HubbleDisplayModeSelect.current_option` reflects updated `displayMode` after `media:state`
- Both entities share the same dict — `player._player_state is display._player_state` after setup

### Service calls (all wrap `HubbleError` → `HomeAssistantError`)
- `turn_on` → `POST /turn-on`
- `turn_off` → `POST /turn-off`
- `media_play` (resume) → `POST /resume`
- `media_pause` → `POST /pause`
- `media_stop` → `POST /stop`
- `play_media` → `POST /play` with mapped content type (`MediaType.MUSIC` → `"audio"`)
- `play_media` with `announce=True` → body includes `"announce": true`
- `play_media` with `extra` dict → `title`, `artist`, `imageUrl`, `displayMode`, `volume` forwarded
- `play_media` with unknown `media_type` → `contentType` omitted (API auto-detects)
- `volume_set(0.5)` → `POST /volume {"level": 0.5}`
- `mute_volume(True)` → `POST /volume {"mute": true}`
- `volume_up` → `POST /volume {"step": "up"}`
- `volume_down` → `POST /volume {"step": "down"}`
- `select_source("HDMI Output")` → maps label to ID → `POST /source {"source": "<id>"}`
- `select_source` with unknown label → passes label as-is; API 400 → `HomeAssistantError`
- `HubbleError` from any command → `HomeAssistantError`

### Display mode select
- `current_option` returns `displayMode` from `_player_state`
- `async_select_option("fullscreen")` → `POST /display {"mode": "fullscreen"}`
- `async_select_option` error → `HomeAssistantError`
- `available` is `False` when `_player_state is None`

### Coordinator extension
- `register_core_handler` stores handler in `_core_handlers`
- `unregister_core_handler` removes handler; no-op if not registered
- `_handle_ws_event`: `"media:state"` dispatched to registered handler, not to the `match` block
- `_handle_ws_event`: `"page:changed"` still handled by the `match` block when no core handler registered
- `async_will_remove_from_hass` calls `unregister_core_handler("media:state")`
- `_handle_ws_event` called with `"media:state"` after `unregister_core_handler` — handler absent, falls through to `match` block, logged as unhandled (no crash)

### `async_media_get_state` (API)
- GET request sent **without** `x-api-key` header
- Returns full state dict on 200
- Raises `HubbleConnectionError` on 401 (not `HubbleAuthError` — no key was sent, so 401 is a connection/server misconfiguration, not an auth failure)
- Raises `HubbleConnectionError` on network failure
