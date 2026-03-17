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
    """Helper: make session.post return a 200 JSON response."""
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
    client._session.get = MagicMock(
        side_effect=aiohttp.ClientError("network error")
    )
    with pytest.raises(HubbleConnectionError):
        await client.async_media_get_state()
