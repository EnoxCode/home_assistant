"""Tests for HubbleApiClient."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from homeassistant.components.hubble.api import (
    HubbleApiClient,
    HubbleAuthError,
    HubbleConnectionError,
)

from . import MOCK_DISCOVERY


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
