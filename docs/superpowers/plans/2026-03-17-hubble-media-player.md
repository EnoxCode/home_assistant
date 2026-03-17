# Hubble Media Player Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `media_player` entity and a `display_mode` select entity to the Hubble HA integration, driven by WebSocket push and controlled via REST.

**Architecture:** Extend the coordinator with a generic core-event handler registry (`register_core_handler`/`unregister_core_handler`). Both entities share one mutable `_player_state` dict updated by a single `on_media_state` closure. All state arrives via `media:state` WS push; service calls hit REST endpoints without waiting for state confirmation.

**Tech Stack:** Python 3.13, Home Assistant `MediaPlayerEntity`, `SelectEntity`, `aiohttp`, `dt_util` for datetime, pytest with `AsyncMock`/`MagicMock`.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `tests/components/hubble/__init__.py` | Modify | Add `MOCK_MEDIA_STATE` |
| `tests/components/hubble/conftest.py` | Modify | Mock `async_media_get_state` in `setup_integration` |
| `tests/components/hubble/test_coordinator.py` | Modify | Add core handler tests |
| `tests/components/hubble/test_websocket.py` | Modify | Assert `"media:state"` in `_DEFAULT_EVENTS` |
| `tests/components/hubble/test_api.py` | Modify | Add media player API method tests |
| `tests/components/hubble/test_media_player.py` | Create | All media player + display select tests |
| `homeassistant/components/hubble/coordinator.py` | Modify | Add `_core_handlers`, `register_core_handler`, `unregister_core_handler`, extend `_handle_ws_event` |
| `homeassistant/components/hubble/websocket.py` | Modify | Add `"media:state"` to `_DEFAULT_EVENTS` |
| `homeassistant/components/hubble/api.py` | Modify | Add 11 media player methods |
| `homeassistant/components/hubble/__init__.py` | Modify | Add `Platform.MEDIA_PLAYER` to `PLATFORMS` |
| `homeassistant/components/hubble/media_player.py` | Create | `HubbleMediaPlayer`, `HubbleDisplayModeSelect`, platform `async_setup_entry` |
| `homeassistant/components/hubble/strings.json` | Modify | Add media player and display mode translations |
| `homeassistant/components/hubble/translations/en.json` | Modify | Mirror strings.json additions |

---

## Task 1: Coordinator Core Handler Infrastructure

**Files:**
- Modify: `homeassistant/components/hubble/coordinator.py`
- Modify: `tests/components/hubble/test_coordinator.py`

- [ ] **Step 1: Write failing tests for `register_core_handler`, `unregister_core_handler`, and `_handle_ws_event` routing**

Add to `tests/components/hubble/test_coordinator.py`:

```python
# ── Core handler registry ───────────────────────────────────────────────────

def test_register_core_handler_stores_handler(coordinator: HubbleCoordinator) -> None:
    """register_core_handler stores the callable under the event name."""
    handler = MagicMock()
    coordinator.register_core_handler("media:state", handler)
    assert coordinator._core_handlers["media:state"] is handler


def test_unregister_core_handler_removes_handler(coordinator: HubbleCoordinator) -> None:
    """unregister_core_handler removes the handler from _core_handlers."""
    handler = MagicMock()
    coordinator.register_core_handler("media:state", handler)
    coordinator.unregister_core_handler("media:state")
    assert "media:state" not in coordinator._core_handlers


def test_unregister_core_handler_noop_if_not_registered(coordinator: HubbleCoordinator) -> None:
    """unregister_core_handler is a no-op for an event with no handler."""
    coordinator.unregister_core_handler("media:state")  # must not raise


def test_handle_ws_event_dispatches_to_core_handler(coordinator: HubbleCoordinator) -> None:
    """_handle_ws_event calls registered core handler with the data dict."""
    handler = MagicMock()
    coordinator.register_core_handler("media:state", handler)
    data = {"state": "playing", "volumeLevel": 0.8}
    coordinator._handle_ws_event("media:state", data)
    handler.assert_called_once_with(data)


def test_handle_ws_event_core_handler_skips_match_block(
    coordinator: HubbleCoordinator,
) -> None:
    """Events handled by a core handler must NOT also reach the match block."""
    handler = MagicMock()
    coordinator.register_core_handler("page:changed", handler)
    original_active_page = coordinator.data["activePage"]
    coordinator._handle_ws_event("page:changed", {"activePage": 99})
    # The match block would have changed activePage — it must NOT have.
    assert coordinator.data["activePage"] == original_active_page
    handler.assert_called_once()


def test_handle_ws_event_unregistered_core_event_still_uses_match_block(
    coordinator: HubbleCoordinator,
) -> None:
    """page:changed still handled by the match block when no core handler registered."""
    coordinator._handle_ws_event("page:changed", {"activePage": 99})
    assert coordinator.data["activePage"] == 99


def test_handle_ws_event_after_unregister_falls_through(
    coordinator: HubbleCoordinator,
) -> None:
    """After unregister, _handle_ws_event treats the event as unhandled (no crash)."""
    handler = MagicMock()
    coordinator.register_core_handler("media:state", handler)
    coordinator.unregister_core_handler("media:state")
    # Should not raise; should not call the old handler
    coordinator._handle_ws_event("media:state", {"state": "idle"})
    handler.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_coordinator.py -k "core_handler" -v
```
Expected: FAIL — `HubbleCoordinator` has no `register_core_handler` attribute

- [ ] **Step 3: Implement coordinator changes**

In `homeassistant/components/hubble/coordinator.py`:

Add to `__init__`:
```python
# Core event handlers registered by platform entities (e.g. media player).
self._core_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}
```

Add two new methods after `register_module_handler`:
```python
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

In `_handle_ws_event`, add the dispatch block **before** the existing `match` statement:
```python
# Core handler registry — checked before the match block.
handler = self._core_handlers.get(event)
if handler:
    handler(data)
    return
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_coordinator.py -k "core_handler" -v
```
Expected: all PASS

- [ ] **Step 5: Run full coordinator test suite to check for regressions**

```bash
pytest tests/components/hubble/test_coordinator.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/coordinator.py \
        tests/components/hubble/test_coordinator.py
git commit -m "feat(hubble): add core handler registry to coordinator"
```

---

## Task 2: WebSocket Media State Subscription

**Files:**
- Modify: `homeassistant/components/hubble/websocket.py`
- Modify: `tests/components/hubble/test_websocket.py`

- [ ] **Step 1: Write failing test**

Add to `tests/components/hubble/test_websocket.py`:

```python
def test_default_events_includes_media_state() -> None:
    """_DEFAULT_EVENTS must include 'media:state' for push-driven media player."""
    from homeassistant.components.hubble.websocket import _DEFAULT_EVENTS
    assert "media:state" in _DEFAULT_EVENTS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/components/hubble/test_websocket.py::test_default_events_includes_media_state -v
```
Expected: FAIL

- [ ] **Step 3: Add `"media:state"` to `_DEFAULT_EVENTS`**

In `homeassistant/components/hubble/websocket.py`, update:
```python
_DEFAULT_EVENTS: frozenset[str] = frozenset(
    {"page:changed", "notification", "notification:dismissed", "media:state"}
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/components/hubble/test_websocket.py::test_default_events_includes_media_state -v
```
Expected: PASS

- [ ] **Step 5: Run full websocket test suite**

```bash
pytest tests/components/hubble/test_websocket.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/websocket.py \
        tests/components/hubble/test_websocket.py
git commit -m "feat(hubble): subscribe to media:state WebSocket event by default"
```

---

## Task 3: `async_media_get_state` API Method

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Modify: `tests/components/hubble/test_api.py`
- Modify: `tests/components/hubble/__init__.py` (add `MOCK_MEDIA_STATE`)

- [ ] **Step 1: Add `MOCK_MEDIA_STATE` to test helpers**

Add to `tests/components/hubble/__init__.py`:

```python
MOCK_MEDIA_STATE = {
    "state": "playing",
    "mediaContentId": "http://nas.local/track.mp3",
    "mediaContentType": "audio",
    "mediaTitle": "Bohemian Rhapsody",
    "mediaArtist": "Queen",
    "mediaImageUrl": "http://nas.local/covers/queen.jpg",
    "mediaDuration": 354.0,
    "mediaPosition": 42.0,
    "mediaPositionUpdatedAt": "2026-03-17T10:23:45.123+00:00",
    "volumeLevel": 0.7,
    "isVolumeMuted": False,
    "displayMode": "none",
    "source": "default",
    "sourceList": [
        {"id": "default", "label": "Default"},
        {"id": "hdmi", "label": "HDMI Output"},
    ],
    "announcing": False,
}
```

- [ ] **Step 2: Write failing tests**

Add to `tests/components/hubble/test_api.py`:

```python
from . import MOCK_DISCOVERY, MOCK_MEDIA_STATE  # add MOCK_MEDIA_STATE to import

# ── async_media_get_state ────────────────────────────────────────────────────

async def test_async_media_get_state_returns_payload(client) -> None:
    """async_media_get_state returns parsed JSON without sending auth header."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=MOCK_MEDIA_STATE)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_media_get_state()

    assert result == MOCK_MEDIA_STATE
    # Must NOT send the x-api-key header
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/state"
    )


async def test_async_media_get_state_raises_connection_error_on_401(client) -> None:
    """async_media_get_state raises HubbleConnectionError on 401 (not auth error).

    No auth header is sent, so a 401 indicates server misconfiguration —
    not an invalid key. Raising HubbleAuthError would incorrectly trigger re-auth.
    """
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.raise_for_status = MagicMock(
        side_effect=aiohttp.ClientResponseError(None, None, status=401)
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleConnectionError):
        await client.async_media_get_state()


async def test_async_media_get_state_raises_connection_error_on_network_failure(
    client,
) -> None:
    """async_media_get_state raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.get = MagicMock(
        side_effect=aiohttp.ClientError("network error")
    )
    with pytest.raises(HubbleConnectionError):
        await client.async_media_get_state()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_api.py -k "media_get_state" -v
```
Expected: FAIL — `HubbleApiClient` has no `async_media_get_state`

- [ ] **Step 4: Implement `async_media_get_state` in `api.py`**

Add to `homeassistant/components/hubble/api.py`:

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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_api.py -k "media_get_state" -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        tests/components/hubble/test_api.py \
        tests/components/hubble/__init__.py
git commit -m "feat(hubble): add async_media_get_state API method"
```

---

## Task 4: Media Player POST API Methods (play, resume, pause, stop, turn-on, turn-off)

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Modify: `tests/components/hubble/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_api.py`. First add a shared helper at module level:

```python
def _make_post_response(payload: dict) -> MagicMock:
    """Return a mock context manager that yields a 200 JSON response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=payload)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    return mock_response


# ── async_media_resume / pause / stop / turn-on / turn-off ──────────────────

async def test_async_media_resume_posts_to_correct_endpoint(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    result = await client.async_media_resume()
    assert result == {"success": True}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/resume",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_pause_posts_to_correct_endpoint(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_pause()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/pause",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_stop_posts_to_correct_endpoint(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_stop()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/stop",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_turn_on_posts_to_correct_endpoint(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_turn_on()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/turn-on",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_turn_off_posts_to_correct_endpoint(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_turn_off()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/turn-off",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


# ── async_media_play ─────────────────────────────────────────────────────────

async def test_async_media_play_sends_required_url(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_play(url="http://nas.local/track.mp3")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"]["url"] == "http://nas.local/track.mp3"
    assert kwargs["json"]["announce"] is False


async def test_async_media_play_includes_optional_fields_when_provided(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_play(
        url="http://nas.local/track.mp3",
        content_type="audio",
        title="Bohemian Rhapsody",
        artist="Queen",
        image_url="http://nas.local/cover.jpg",
        volume=0.8,
        display_mode="none",
        announce=True,
    )
    _, kwargs = client._session.post.call_args
    body = kwargs["json"]
    assert body["contentType"] == "audio"
    assert body["title"] == "Bohemian Rhapsody"
    assert body["artist"] == "Queen"
    assert body["imageUrl"] == "http://nas.local/cover.jpg"
    assert body["volume"] == 0.8
    assert body["displayMode"] == "none"
    assert body["announce"] is True


async def test_async_media_play_omits_none_optional_fields(client) -> None:
    client._session.post = MagicMock(return_value=_make_post_response({"success": True}))
    await client.async_media_play(url="http://nas.local/track.mp3")
    _, kwargs = client._session.post.call_args
    body = kwargs["json"]
    assert "contentType" not in body
    assert "title" not in body
    assert "artist" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_api.py -k "async_media_resume or async_media_pause or async_media_stop or async_media_turn or async_media_play" -v
```
Expected: FAIL

- [ ] **Step 3: Implement the six methods in `api.py`**

```python
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
    """POST /api/media-player/play."""
    payload: dict[str, Any] = {"url": url, "announce": announce}
    if content_type is not None:
        payload["contentType"] = content_type
    if display_mode is not None:
        payload["displayMode"] = display_mode
    if title is not None:
        payload["title"] = title
    if artist is not None:
        payload["artist"] = artist
    if image_url is not None:
        payload["imageUrl"] = image_url
    if volume is not None:
        payload["volume"] = volume
    return await self._async_post("/api/media-player/play", payload)

async def async_media_resume(self) -> dict[str, Any]:
    """POST /api/media-player/resume."""
    return await self._async_post("/api/media-player/resume")

async def async_media_pause(self) -> dict[str, Any]:
    """POST /api/media-player/pause."""
    return await self._async_post("/api/media-player/pause")

async def async_media_stop(self) -> dict[str, Any]:
    """POST /api/media-player/stop."""
    return await self._async_post("/api/media-player/stop")

async def async_media_turn_on(self) -> dict[str, Any]:
    """POST /api/media-player/turn-on."""
    return await self._async_post("/api/media-player/turn-on")

async def async_media_turn_off(self) -> dict[str, Any]:
    """POST /api/media-player/turn-off."""
    return await self._async_post("/api/media-player/turn-off")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_api.py -k "async_media_resume or async_media_pause or async_media_stop or async_media_turn or async_media_play" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        tests/components/hubble/test_api.py
git commit -m "feat(hubble): add media player play/pause/stop/turn-on/off API methods"
```

---

## Task 5: Volume, Display, Source API Methods

**Files:**
- Modify: `homeassistant/components/hubble/api.py`
- Modify: `tests/components/hubble/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_api.py`:

```python
# ── Volume / display / source ────────────────────────────────────────────────

async def test_async_media_set_volume_level(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "volumeLevel": 0.5, "isVolumeMuted": False})
    )
    await client.async_media_set_volume_level(0.5)
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"level": 0.5}
    assert "http://kitchen-screen:3000/api/media-player/volume" in client._session.post.call_args[0][0]


async def test_async_media_mute_volume(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "volumeLevel": 0.5, "isVolumeMuted": True})
    )
    await client.async_media_mute_volume(True)
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"mute": True}


async def test_async_media_volume_step_up(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "volumeLevel": 0.8, "isVolumeMuted": False})
    )
    await client.async_media_volume_step("up")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"step": "up"}


async def test_async_media_volume_step_down(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "volumeLevel": 0.6, "isVolumeMuted": False})
    )
    await client.async_media_volume_step("down")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"step": "down"}


async def test_async_media_set_display(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "displayMode": "fullscreen"})
    )
    await client.async_media_set_display("fullscreen")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"mode": "fullscreen"}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/display",
        headers={"x-api-key": "test-api-key"},
        json={"mode": "fullscreen"},
    )


async def test_async_media_set_source(client) -> None:
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True, "source": "hdmi"})
    )
    await client.async_media_set_source("hdmi")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"source": "hdmi"}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/source",
        headers={"x-api-key": "test-api-key"},
        json={"source": "hdmi"},
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_api.py -k "volume or display or set_source" -v
```
Expected: FAIL

- [ ] **Step 3: Implement the five methods in `api.py`**

```python
async def async_media_set_volume_level(self, level: float) -> dict[str, Any]:
    """POST /api/media-player/volume with {"level": level}."""
    return await self._async_post("/api/media-player/volume", {"level": level})

async def async_media_mute_volume(self, mute: bool) -> dict[str, Any]:
    """POST /api/media-player/volume with {"mute": mute}."""
    return await self._async_post("/api/media-player/volume", {"mute": mute})

async def async_media_volume_step(self, direction: str) -> dict[str, Any]:
    """POST /api/media-player/volume with {"step": "up" | "down"}."""
    return await self._async_post("/api/media-player/volume", {"step": direction})

async def async_media_set_display(self, mode: str) -> dict[str, Any]:
    """POST /api/media-player/display with {"mode": mode}."""
    return await self._async_post("/api/media-player/display", {"mode": mode})

async def async_media_set_source(self, source_id: str) -> dict[str, Any]:
    """POST /api/media-player/source with {"source": source_id}."""
    return await self._async_post("/api/media-player/source", {"source": source_id})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_api.py -k "volume or display or set_source" -v
```
Expected: all PASS

- [ ] **Step 5: Run full API test suite**

```bash
pytest tests/components/hubble/test_api.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add homeassistant/components/hubble/api.py \
        tests/components/hubble/test_api.py
git commit -m "feat(hubble): add media player volume/display/source API methods"
```

---

## Task 6: Platform Skeleton and Setup

**Files:**
- Create: `homeassistant/components/hubble/media_player.py`
- Modify: `homeassistant/components/hubble/__init__.py`
- Modify: `tests/components/hubble/conftest.py`
- Create: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests for platform setup**

Create `tests/components/hubble/test_media_player.py`:

```python
"""Tests for Hubble media player and display mode select entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

from . import MOCK_MEDIA_STATE, MOCK_USER_INPUT
from homeassistant.components.hubble.const import DOMAIN


@pytest.fixture
async def setup_media_player(hass: HomeAssistant):
    """Set up Hubble integration with a mocked media player state.

    Returns the config entry. All API calls are mocked; WebSocket is suppressed.
    """
    from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT

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
        mock_client.async_media_get_state = AsyncMock(return_value=dict(MOCK_MEDIA_STATE))
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


async def test_initial_state_fetched(
    hass: HomeAssistant, setup_media_player
) -> None:
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


async def test_entities_unavailable_when_initial_fetch_fails(
    hass: HomeAssistant,
) -> None:
    """Both entities start unavailable when async_media_get_state raises."""
    from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT
    from homeassistant.components.hubble.api import HubbleConnectionError

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py::test_media_player_entity_created -v
```
Expected: FAIL — `media_player.kitchen_screen_media_player` not found

- [ ] **Step 3: Mock `async_media_get_state` in the shared `setup_integration` fixture**

In `tests/components/hubble/conftest.py`, add one line to the `setup_integration` fixture so existing tests keep passing when `Platform.MEDIA_PLAYER` is added (the media player platform calls `async_media_get_state` during setup):

```python
mock_client.async_media_get_state = AsyncMock(return_value=dict(MOCK_MEDIA_STATE))
```

Add it alongside the other `mock_client` method assignments (after the `async_get_connector_state` line).

Also add `MOCK_MEDIA_STATE` to the import at the top of conftest.py:

```python
from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_MEDIA_STATE, MOCK_NOTIFY_COUNT, MOCK_USER_INPUT
```

- [ ] **Step 4: Add `Platform.MEDIA_PLAYER` to `__init__.py`**

In `homeassistant/components/hubble/__init__.py`:
```python
PLATFORMS = [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.SELECT, Platform.SENSOR]
```

- [ ] **Step 5: Create `media_player.py` skeleton**

Create `homeassistant/components/hubble/media_player.py`:

```python
"""Hubble media player and display mode select entities."""

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
from homeassistant.components.select import SelectEntity
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
    """Set up Hubble media player and display mode select entities."""
    coordinator = entry.runtime_data

    try:
        initial_state: dict[str, Any] | None = (
            await coordinator.client.async_media_get_state()
        )
    except HubbleError:
        _LOGGER.warning("Failed to fetch initial Hubble media player state")
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
            # display already shares the same dict — no reassignment needed
        player.async_write_ha_state()
        display.async_write_ha_state()

    coordinator.register_core_handler("media:state", on_media_state)


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
        self._player_state: dict[str, Any] | None = None
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
        return self._player_state is not None

    async def async_will_remove_from_hass(self) -> None:
        """Clean up core handler when entity is removed."""
        self.coordinator.unregister_core_handler("media:state")


class HubbleDisplayModeSelect(SelectEntity):
    """Hubble display mode select entity."""

    _attr_has_entity_name = True
    _attr_translation_key = "display_mode"
    _attr_options = DISPLAY_MODES

    def __init__(self, coordinator, entry: HubbleConfigEntry) -> None:
        """Initialise the display mode select entity."""
        self._player_state: dict[str, Any] | None = None
        self._attr_unique_id = f"{entry.entry_id}_display_mode"
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
        return self._player_state is not None

    @property
    def current_option(self) -> str | None:
        """Return the current display mode."""
        if self._player_state is None:
            return None
        return self._player_state.get("displayMode")

    async def async_select_option(self, option: str) -> None:
        """Change the display mode."""
        try:
            await self.coordinator.client.async_media_set_display(option)
        except HubbleError as err:
            raise HomeAssistantError(str(err)) from err
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -v
```
Expected: all PASS

- [ ] **Step 6: Run full suite to check for regressions**

```bash
pytest tests/components/hubble/ -v
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add homeassistant/components/hubble/__init__.py \
        homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add media player platform skeleton with both entities"
```

---

## Task 7: State Mapping and Read-Only Properties

**Files:**
- Modify: `homeassistant/components/hubble/media_player.py`
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
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
    coordinator._handle_ws_event("media:state", {**MOCK_MEDIA_STATE, "state": hubble_state})
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.state == expected


async def test_media_content_type_audio_maps_to_music(
    hass: HomeAssistant, setup_media_player
) -> None:
    """mediaContentType 'audio' maps to MediaType.MUSIC."""
    entry, _ = setup_media_player
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_content_type") == "music"


async def test_media_content_type_video_maps_to_video(
    hass: HomeAssistant, setup_media_player
) -> None:
    """mediaContentType 'video' maps to MediaType.VIDEO."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event("media:state", {**MOCK_MEDIA_STATE, "mediaContentType": "video"})
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_content_type") == "video"


async def test_media_title_exposed(hass: HomeAssistant, setup_media_player) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_title") == "Bohemian Rhapsody"


async def test_media_artist_exposed(hass: HomeAssistant, setup_media_player) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_artist") == "Queen"


async def test_entity_picture_uses_media_image_url(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_image_url (not entity_picture) carries the artwork URL."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("entity_picture") == "http://nas.local/covers/queen.jpg"


async def test_volume_level_exposed(hass: HomeAssistant, setup_media_player) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("volume_level") == 0.7


async def test_is_volume_muted_exposed(hass: HomeAssistant, setup_media_player) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("is_volume_muted") is False


async def test_extra_state_attributes_display_mode(
    hass: HomeAssistant, setup_media_player
) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("display_mode") == "none"


async def test_extra_state_attributes_announcing(
    hass: HomeAssistant, setup_media_player
) -> None:
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("announcing") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "state_mapping or content_type or media_title or media_artist or entity_picture or volume or announcing or display_mode" -v
```
Expected: most FAIL — properties not yet implemented

- [ ] **Step 3: Add properties to `HubbleMediaPlayer`**

Add these properties to the `HubbleMediaPlayer` class in `media_player.py`:

```python
@property
def state(self) -> MediaPlayerState | None:
    if self._player_state is None:
        return None
    return _HUBBLE_STATE_MAP.get(self._player_state.get("state", ""))

@property
def media_content_id(self) -> str | None:
    return (self._player_state or {}).get("mediaContentId")

@property
def media_content_type(self) -> MediaType | None:
    raw = (self._player_state or {}).get("mediaContentType")
    if raw == "audio":
        return MediaType.MUSIC
    if raw == "video":
        return MediaType.VIDEO
    return None

@property
def media_title(self) -> str | None:
    return (self._player_state or {}).get("mediaTitle")

@property
def media_artist(self) -> str | None:
    return (self._player_state or {}).get("mediaArtist")

@property
def media_image_url(self) -> str | None:
    return (self._player_state or {}).get("mediaImageUrl")

@property
def media_duration(self) -> float | None:
    return (self._player_state or {}).get("mediaDuration")

@property
def volume_level(self) -> float | None:
    return (self._player_state or {}).get("volumeLevel")

@property
def is_volume_muted(self) -> bool | None:
    return (self._player_state or {}).get("isVolumeMuted")

@property
def extra_state_attributes(self) -> dict[str, Any]:
    if self._player_state is None:
        return {}
    return {
        "display_mode": self._player_state.get("displayMode"),
        "announcing": self._player_state.get("announcing"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -k "state_mapping or content_type or media_title or media_artist or entity_picture or volume or announcing or display_mode" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add state mapping and read-only media player properties"
```

---

## Task 8: Position Extrapolation

**Files:**
- Modify: `homeassistant/components/hubble/media_player.py`
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
# ── Position extrapolation ───────────────────────────────────────────────────

async def test_media_position_extrapolated_when_playing(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position adds elapsed time since mediaPositionUpdatedAt when playing."""
    import datetime
    from unittest.mock import patch as mock_patch

    entry, _ = setup_media_player
    coordinator = entry.runtime_data

    # Freeze time: 10 seconds after the position timestamp in MOCK_MEDIA_STATE
    # (mediaPositionUpdatedAt = "2026-03-17T10:23:45.123+00:00")
    frozen = datetime.datetime(2026, 3, 17, 10, 23, 55, 123000, tzinfo=datetime.timezone.utc)
    with mock_patch("homeassistant.util.dt.utcnow", return_value=frozen):
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
        {**MOCK_MEDIA_STATE, "state": "playing", "mediaPositionUpdatedAt": "not-a-date"},
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("media_position") == 42.0


async def test_media_position_capped_at_duration(
    hass: HomeAssistant, setup_media_player
) -> None:
    """media_position never exceeds mediaDuration."""
    import datetime
    from unittest.mock import patch as mock_patch

    entry, _ = setup_media_player
    coordinator = entry.runtime_data

    # Advance far past the timestamp (elapsed >> duration of 354.0)
    frozen = datetime.datetime(2026, 3, 17, 10, 40, 25, 123000, tzinfo=datetime.timezone.utc)
    with mock_patch("homeassistant.util.dt.utcnow", return_value=frozen):
        coordinator._handle_ws_event("media:state", dict(MOCK_MEDIA_STATE))
        await hass.async_block_till_done()
        state = hass.states.get("media_player.kitchen_screen_media_player")
        # Duration is 354.0 — must be capped
        assert state.attributes.get("media_position") <= 354.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "position" -v
```
Expected: FAIL

- [ ] **Step 3: Implement position properties**

Add to `HubbleMediaPlayer` in `media_player.py`:

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

@property
def media_position_updated_at(self):
    if self._player_state is None:
        return None
    raw = self._player_state.get("mediaPositionUpdatedAt")
    if raw is None:
        return None
    return dt_util.parse_datetime(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -k "position" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add media position extrapolation with dt_util"
```

---

## Task 9: Source Properties

**Files:**
- Modify: `homeassistant/components/hubble/media_player.py`
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
# ── Source properties ─────────────────────────────────────────────────────────

async def test_source_returns_label_for_active_source(
    hass: HomeAssistant, setup_media_player
) -> None:
    """source property returns the label matching the active source ID."""
    # MOCK_MEDIA_STATE source="default", sourceList has id="default" label="Default"
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source") == "Default"


async def test_source_returns_raw_id_when_not_in_source_list(
    hass: HomeAssistant, setup_media_player
) -> None:
    """source falls back to the raw ID when it's not in sourceList."""
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
    """source property returns None when Hubble reports source as null."""
    entry, _ = setup_media_player
    coordinator = entry.runtime_data
    coordinator._handle_ws_event(
        "media:state", {**MOCK_MEDIA_STATE, "source": None}
    )
    await hass.async_block_till_done()
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source") is None


async def test_source_list_returns_labels(
    hass: HomeAssistant, setup_media_player
) -> None:
    """source_list exposes display labels, not device IDs."""
    state = hass.states.get("media_player.kitchen_screen_media_player")
    assert state.attributes.get("source_list") == ["Default", "HDMI Output"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "source" -v
```
Expected: FAIL

- [ ] **Step 3: Add source properties to `HubbleMediaPlayer`**

```python
@property
def source(self) -> str | None:
    if self._player_state is None:
        return None
    active_id = self._player_state.get("source")
    if active_id is None:
        return None
    source_list = self._player_state.get("sourceList", [])
    return next(
        (s["label"] for s in source_list if s["id"] == active_id),
        active_id,  # fallback: return raw ID if not found in list
    )

@property
def source_list(self) -> list[str] | None:
    if self._player_state is None:
        return None
    return [s["label"] for s in self._player_state.get("sourceList", [])]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -k "source" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add source and source_list properties to media player"
```

---

## Task 10: Playback and Volume Service Methods

**Files:**
- Modify: `homeassistant/components/hubble/media_player.py`
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
# ── Service methods ───────────────────────────────────────────────────────────

async def test_turn_on_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_turn_on = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "turn_on",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_turn_on.assert_called_once()


async def test_turn_off_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_turn_off = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "turn_off",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_turn_off.assert_called_once()


async def test_media_play_calls_resume(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_resume = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "media_play",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_resume.assert_called_once()


async def test_media_pause_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_pause = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "media_pause",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_pause.assert_called_once()


async def test_media_stop_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_stop = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "media_stop",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_stop.assert_called_once()


async def test_volume_set_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_set_volume_level = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.5, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player", "volume_set",
        {"entity_id": "media_player.kitchen_screen_media_player", "volume_level": 0.5},
        blocking=True,
    )
    mock_client.async_media_set_volume_level.assert_called_once_with(0.5)


async def test_mute_volume_calls_api(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_mute_volume = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.7, "isVolumeMuted": True}
    )
    await hass.services.async_call(
        "media_player", "volume_mute",
        {"entity_id": "media_player.kitchen_screen_media_player", "is_volume_muted": True},
        blocking=True,
    )
    mock_client.async_media_mute_volume.assert_called_once_with(True)


async def test_volume_up_calls_step_up(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_volume_step = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.8, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player", "volume_up",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_volume_step.assert_called_once_with("up")


async def test_volume_down_calls_step_down(hass: HomeAssistant, setup_media_player) -> None:
    entry, mock_client = setup_media_player
    mock_client.async_media_volume_step = AsyncMock(
        return_value={"success": True, "volumeLevel": 0.6, "isVolumeMuted": False}
    )
    await hass.services.async_call(
        "media_player", "volume_down",
        {"entity_id": "media_player.kitchen_screen_media_player"},
        blocking=True,
    )
    mock_client.async_media_volume_step.assert_called_once_with("down")


async def test_service_error_raises_home_assistant_error(
    hass: HomeAssistant, setup_media_player
) -> None:
    """HubbleError from any service call surfaces as HomeAssistantError."""
    from homeassistant.components.hubble.api import HubbleConnectionError
    from homeassistant.exceptions import HomeAssistantError

    entry, mock_client = setup_media_player
    mock_client.async_media_turn_on = AsyncMock(
        side_effect=HubbleConnectionError("timeout")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player", "turn_on",
            {"entity_id": "media_player.kitchen_screen_media_player"},
            blocking=True,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "turn_on or turn_off or media_play or media_pause or media_stop or volume" -v
```
Expected: FAIL

- [ ] **Step 3: Add service methods to `HubbleMediaPlayer`**

```python
async def async_turn_on(self) -> None:
    try:
        await self.coordinator.client.async_media_turn_on()
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_turn_off(self) -> None:
    try:
        await self.coordinator.client.async_media_turn_off()
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_media_play(self) -> None:
    try:
        await self.coordinator.client.async_media_resume()
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_media_pause(self) -> None:
    try:
        await self.coordinator.client.async_media_pause()
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_media_stop(self) -> None:
    try:
        await self.coordinator.client.async_media_stop()
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_set_volume_level(self, volume: float) -> None:
    try:
        await self.coordinator.client.async_media_set_volume_level(volume)
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_mute_volume(self, mute: bool) -> None:
    try:
        await self.coordinator.client.async_media_mute_volume(mute)
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_volume_up(self) -> None:
    try:
        await self.coordinator.client.async_media_volume_step("up")
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err

async def async_volume_down(self) -> None:
    try:
        await self.coordinator.client.async_media_volume_step("down")
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -k "turn_on or turn_off or media_play or media_pause or media_stop or volume or service_error" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add playback and volume service methods to media player"
```

---

## Task 11: `play_media` and `select_source`

**Files:**
- Modify: `homeassistant/components/hubble/media_player.py`
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
# ── play_media ────────────────────────────────────────────────────────────────

async def test_play_media_maps_music_content_type(
    hass: HomeAssistant, setup_media_player
) -> None:
    """MediaType.MUSIC maps to contentType 'audio' in the POST body."""
    entry, mock_client = setup_media_player
    mock_client.async_media_play = AsyncMock(return_value={"success": True})
    await hass.services.async_call(
        "media_player", "play_media",
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
        "media_player", "play_media",
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
        "media_player", "play_media",
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
        "media_player", "play_media",
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
    mock_client.async_media_set_source = AsyncMock(return_value={"success": True, "source": "hdmi"})
    await hass.services.async_call(
        "media_player", "select_source",
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
    from homeassistant.components.hubble.api import HubbleConnectionError
    from homeassistant.exceptions import HomeAssistantError

    entry, mock_client = setup_media_player
    mock_client.async_media_set_source = AsyncMock(
        side_effect=HubbleConnectionError("Source not available")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player", "select_source",
            {
                "entity_id": "media_player.kitchen_screen_media_player",
                "source": "Bluetooth Headphones",
            },
            blocking=True,
        )
    # Unknown label passed as-is to the API
    mock_client.async_media_set_source.assert_called_once_with("Bluetooth Headphones")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "play_media or select_source" -v
```
Expected: FAIL

- [ ] **Step 3: Implement `async_play_media` and `async_select_source`**

Add to `HubbleMediaPlayer` in `media_player.py`:

```python
async def async_play_media(
    self, media_type: MediaType | str, media_id: str, **kwargs: Any
) -> None:
    announce: bool = kwargs.get("announce", False)
    extra: dict[str, Any] = kwargs.get(ATTR_MEDIA_EXTRA, {})
    content_type = _MEDIA_TYPE_MAP.get(str(media_type))
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
    source_list = (self._player_state or {}).get("sourceList", [])
    source_id = next(
        (s["id"] for s in source_list if s["label"] == source),
        source,  # fallback: pass raw string; API returns 400 → HomeAssistantError
    )
    try:
        await self.coordinator.client.async_media_set_source(source_id)
    except HubbleError as err:
        raise HomeAssistantError(str(err)) from err
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/components/hubble/test_media_player.py -k "play_media or select_source" -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/media_player.py \
        tests/components/hubble/test_media_player.py
git commit -m "feat(hubble): add play_media and select_source to media player"
```

---

## Task 12: Display Mode Select and WS Event Flow

**Files:**
- Modify: `tests/components/hubble/test_media_player.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/components/hubble/test_media_player.py`:

```python
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
    entry, mock_client = setup_media_player
    mock_client.async_media_set_display = AsyncMock(
        return_value={"success": True, "displayMode": "fullscreen"}
    )
    await hass.services.async_call(
        "select", "select_option",
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
    from homeassistant.components.hubble.api import HubbleConnectionError
    from homeassistant.exceptions import HomeAssistantError

    entry, mock_client = setup_media_player
    mock_client.async_media_set_display = AsyncMock(
        side_effect=HubbleConnectionError("bad mode")
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select", "select_option",
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
    """After recovery from None, both entities share the same _player_state dict."""
    from . import MOCK_DASHBOARD_STATE, MOCK_DISCOVERY, MOCK_NOTIFY_COUNT
    from homeassistant.components.hubble.api import HubbleConnectionError
    from homeassistant.components import hubble

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

        coordinator = entry.runtime_data
        # Simulate first WS event arriving after failed initial fetch
        coordinator._handle_ws_event("media:state", dict(MOCK_MEDIA_STATE))
        await hass.async_block_till_done()

        player = hass.states.get("media_player.kitchen_screen_media_player")
        display = hass.states.get("select.kitchen_screen_display_mode")
        assert player.state == "playing"
        assert display.state == "none"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/components/hubble/test_media_player.py -k "display_select or ws_event or shared_dict" -v
```
Expected: FAIL (display select tests may partially pass from earlier work, WS tests should fail)

- [ ] **Step 3: Run tests — they should pass** (display mode select was implemented in Task 6)

```bash
pytest tests/components/hubble/test_media_player.py -k "display_select or ws_event or shared_dict" -v
```

If any fail, check `HubbleDisplayModeSelect.async_select_option` error wrapping and the `on_media_state` closure in `async_setup_entry`.

- [ ] **Step 4: Run full media player test suite**

```bash
pytest tests/components/hubble/test_media_player.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/components/hubble/test_media_player.py
git commit -m "test(hubble): add display select and WS event flow tests"
```

---

## Task 13: Strings and Translations

**Files:**
- Modify: `homeassistant/components/hubble/strings.json`
- Modify: `homeassistant/components/hubble/translations/en.json`

- [ ] **Step 1: Read current strings.json**

```bash
cat homeassistant/components/hubble/strings.json
```

- [ ] **Step 2: Add entries to `strings.json`**

Merge into the `"entity"` section. Add under `"media_player"`:

```json
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
```

Note: `HubbleDisplayModeSelect` is registered via the `media_player` platform's `async_add_entities`, so its translation lives under `entity.media_player.display_mode` (not `entity.select`).

- [ ] **Step 3: Mirror the same additions in `translations/en.json`**

The `translations/en.json` file is the English locale and must exactly mirror `strings.json`.

- [ ] **Step 4: Verify JSON is valid**

```bash
python3 -c "import json; json.load(open('homeassistant/components/hubble/strings.json'))"
python3 -c "import json; json.load(open('homeassistant/components/hubble/translations/en.json'))"
```
Expected: no output (no errors)

- [ ] **Step 5: Commit**

```bash
git add homeassistant/components/hubble/strings.json \
        homeassistant/components/hubble/translations/en.json
git commit -m "feat(hubble): add media player and display mode translations"
```

---

## Task 14: Final Verification

- [ ] **Step 1: Run the full Hubble test suite**

```bash
pytest tests/components/hubble/ -v
```
Expected: all PASS, no failures

- [ ] **Step 2: Run linting on changed files**

```bash
./script/lint
```
Expected: no errors. Fix any ruff or pylint issues before committing.

- [ ] **Step 3: Run type checking on the hubble component**

```bash
mypy homeassistant/components/hubble/
```
Expected: no errors. Common issues to watch for:
- Missing return type annotations
- `_player_state` access without `None` guard
- Untyped `coordinator` parameter in `__init__` — add `HubbleCoordinator` type annotation

- [ ] **Step 4: Final commit if any lint fixes were needed**

```bash
git add -p  # stage only the lint fixes
git commit -m "fix(hubble): address lint and type errors in media player"
```
