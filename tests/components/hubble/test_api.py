"""Tests for HubbleApiClient."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from homeassistant.components.hubble.api import (
    HubbleApiClient,
    HubbleAuthError,
    HubbleConnectionError,
)

from . import MOCK_DISCOVERY, MOCK_MEDIA_STATE


@pytest.fixture
def client():
    """Return a HubbleApiClient with a mock session."""
    session = MagicMock()
    return HubbleApiClient(
        host="kitchen-screen",
        port=3000,
        api_key="test-api-key",
        session=session,
    )


async def test_async_discover_returns_payload(client) -> None:
    """async_discover returns the parsed JSON from GET /api/ws/events."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=MOCK_DISCOVERY)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_discover()

    assert result == MOCK_DISCOVERY
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/ws/events",
        headers={"x-api-key": "test-api-key"},
    )


async def test_async_discover_raises_auth_error_on_401(client) -> None:
    """async_discover raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_discover()


async def test_async_discover_raises_connection_error(client) -> None:
    """async_discover raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_discover()


async def test_async_get_connector_state_returns_payload(client) -> None:
    """async_get_connector_state returns parsed JSON from connector-state endpoint."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={"timer:started": {"slug": "timer-1", "mode": "countdown"}}
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_get_connector_state("hubble-timer")

    assert result == {"timer:started": {"slug": "timer-1", "mode": "countdown"}}
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/dashboard/connector-state/hubble-timer",
        headers={"x-api-key": "test-api-key"},
    )


async def test_async_get_connector_state_raises_auth_error_on_401(client) -> None:
    """async_get_connector_state raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_get_connector_state("hubble-timer")


async def test_async_get_connector_state_raises_connection_error(client) -> None:
    """async_get_connector_state raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.get = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_get_connector_state("hubble-timer")


def _mock_post_response(session, return_value):
    """Set session.post to return a 200 JSON response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=return_value)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(return_value=mock_response)


async def test_async_timer_start_with_duration_and_label(client) -> None:
    """async_timer_start sends slug, duration, and label to the start endpoint."""
    _mock_post_response(client._session, {"ok": True})

    result = await client.async_timer_start("timer-1", duration=300, label="Pasta")

    assert result == {"ok": True}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/start",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1", "duration": 300, "label": "Pasta"},
    )


async def test_async_timer_start_without_duration_omits_key(client) -> None:
    """async_timer_start without duration sends only slug (stopwatch mode)."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_start("timer-1")

    sent_json = client._session.post.call_args[1]["json"]
    assert sent_json == {"slug": "timer-1"}
    assert "duration" not in sent_json


async def test_async_timer_pause(client) -> None:
    """async_timer_pause POSTs slug to the pause endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_pause("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/pause",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_resume(client) -> None:
    """async_timer_resume POSTs slug to the resume endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_resume("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/resume",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_reset(client) -> None:
    """async_timer_reset POSTs slug to the reset endpoint."""
    _mock_post_response(client._session, {"ok": True})

    await client.async_timer_reset("timer-1")

    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/module/hubble-timer/api/reset",
        headers={"x-api-key": "test-api-key"},
        json={"slug": "timer-1"},
    )


async def test_async_timer_action_raises_auth_error_on_401(client) -> None:
    """Timer action raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.post = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_timer_pause("timer-1")


async def test_async_timer_action_raises_connection_error(client) -> None:
    """Timer action raises HubbleConnectionError on aiohttp.ClientError."""
    client._session.post = MagicMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_timer_reset("timer-1")


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
    client._session.get = MagicMock(side_effect=aiohttp.ClientError("network error"))
    with pytest.raises(HubbleConnectionError):
        await client.async_media_get_state()


def _make_post_response(payload: dict) -> MagicMock:
    """Return a context manager that yields a 200 JSON response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=payload)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    return mock_response


# ── async_media_resume / pause / stop / turn-on / turn-off ──────────────────


async def test_async_media_resume_posts_to_correct_endpoint(client) -> None:
    """Test async_media_resume POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
    result = await client.async_media_resume()
    assert result == {"success": True}
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/resume",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_pause_posts_to_correct_endpoint(client) -> None:
    """Test async_media_pause POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
    await client.async_media_pause()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/pause",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_media_stop_posts_to_correct_endpoint(client) -> None:
    """Test async_media_stop POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
    await client.async_media_stop()
    client._session.post.assert_called_once_with(
        "http://kitchen-screen:3000/api/media-player/stop",
        headers={"x-api-key": "test-api-key"},
        json={},
    )


async def test_async_execute_command_gets_correct_endpoint(client) -> None:
    """async_execute_command GETs the commands execute endpoint for a given slug."""
    execute_result = {"ok": True, "stdout": "true", "stderr": "", "exitCode": 0}
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=execute_result)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    result = await client.async_execute_command("screen-status")

    assert result == execute_result
    client._session.get.assert_called_once_with(
        "http://kitchen-screen:3000/api/commands/screen-status/execute",
        headers={"x-api-key": "test-api-key"},
    )


async def test_async_execute_command_raises_auth_error_on_401(client) -> None:
    """async_execute_command raises HubbleAuthError on HTTP 401."""
    mock_response = MagicMock()
    mock_response.status = 401
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    client._session.get = MagicMock(return_value=mock_response)

    with pytest.raises(HubbleAuthError):
        await client.async_execute_command("screen-on")


# ── async_media_play ─────────────────────────────────────────────────────────


async def test_async_media_play_sends_required_url(client) -> None:
    """Test async_media_play sends required url parameter."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
    await client.async_media_play(url="http://nas.local/track.mp3")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"]["url"] == "http://nas.local/track.mp3"
    assert kwargs["json"]["announce"] is False


async def test_async_media_play_includes_optional_fields_when_provided(
    client,
) -> None:
    """Test async_media_play includes optional fields when provided."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
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
    """Test async_media_play omits None optional fields from payload."""
    client._session.post = MagicMock(
        return_value=_make_post_response({"success": True})
    )
    await client.async_media_play(url="http://nas.local/track.mp3")
    _, kwargs = client._session.post.call_args
    body = kwargs["json"]
    assert "contentType" not in body
    assert "title" not in body
    assert "artist" not in body


# ── Volume / display / source ────────────────────────────────────────────────


async def test_async_media_set_volume_level(client) -> None:
    """Test async_media_set_volume_level POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response(
            {"success": True, "volumeLevel": 0.5, "isVolumeMuted": False}
        )
    )
    await client.async_media_set_volume_level(0.5)
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"level": 0.5}
    assert (
        "http://kitchen-screen:3000/api/media-player/volume"
        in client._session.post.call_args[0][0]
    )


async def test_async_media_mute_volume(client) -> None:
    """Test async_media_mute_volume POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response(
            {"success": True, "volumeLevel": 0.5, "isVolumeMuted": True}
        )
    )
    await client.async_media_mute_volume(True)
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"mute": True}


async def test_async_media_volume_step_up(client) -> None:
    """Test async_media_volume_step('up') POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response(
            {"success": True, "volumeLevel": 0.8, "isVolumeMuted": False}
        )
    )
    await client.async_media_volume_step("up")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"step": "up"}


async def test_async_media_volume_step_down(client) -> None:
    """Test async_media_volume_step('down') POSTs to the correct endpoint."""
    client._session.post = MagicMock(
        return_value=_make_post_response(
            {"success": True, "volumeLevel": 0.6, "isVolumeMuted": False}
        )
    )
    await client.async_media_volume_step("down")
    _, kwargs = client._session.post.call_args
    assert kwargs["json"] == {"step": "down"}


async def test_async_media_set_display(client) -> None:
    """Test async_media_set_display POSTs to the correct endpoint."""
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
    """Test async_media_set_source POSTs to the correct endpoint."""
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
