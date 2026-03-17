"""Tests for HubbleWebSocketClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from homeassistant.components.hubble.api import HubbleAuthError, HubbleConnectionError
from homeassistant.components.hubble.websocket import HubbleWebSocketClient

# ── Helpers ────────────────────────────────────────────────────────────────────

def _ws_message(msg_type: aiohttp.WSMsgType, data=None) -> aiohttp.WSMessage:
    """Build an aiohttp WSMessage."""
    return aiohttp.WSMessage(type=msg_type, data=data, extra=None)


def _make_ws(messages: list[aiohttp.WSMessage]) -> MagicMock:
    """Return a mock ClientWebSocketResponse that yields messages."""

    async def _aiter():
        for msg in messages:
            yield msg

    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()
    ws.__aiter__ = MagicMock(return_value=_aiter())
    return ws


def _make_client(ws_mock=None, on_event=None):
    """Return a HubbleWebSocketClient with a mock session."""
    session = MagicMock()
    if ws_mock is not None:
        session.ws_connect = AsyncMock(return_value=ws_mock)
    client = HubbleWebSocketClient(
        host="kitchen-screen",
        port=3000,
        api_key="test-api-key",
        session=session,
        on_event=on_event or (lambda event, data: None),
    )
    return client, session


# ── async_connect ──────────────────────────────────────────────────────────────

async def test_connect_sends_auth_and_subscribe() -> None:
    """async_connect sends auth message then subscribe message."""
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()

    # Simulate auth success response
    auth_response = aiohttp.WSMessage(
        type=aiohttp.WSMsgType.TEXT,
        data=json.dumps({"authenticated": True, "clientType": "external"}),
        extra=None,
    )
    ws.receive = AsyncMock(return_value=auth_response)

    client, session = _make_client(ws_mock=ws)
    await client.async_connect()

    # First send: auth
    first_call = json.loads(ws.send_str.call_args_list[0][0][0])
    assert first_call == {"action": "auth", "apiKey": "test-api-key"}

    # Second send: subscribe with core events
    second_call = json.loads(ws.send_str.call_args_list[1][0][0])
    assert second_call["action"] == "subscribe"
    assert set(second_call["events"]) == {
        "page:changed",
        "notification",
        "notification:dismissed",
    }


async def test_connect_raises_auth_error_on_error_response() -> None:
    """async_connect raises HubbleAuthError when server returns {"error": ...}."""
    ws = MagicMock()
    ws.send_str = AsyncMock()
    ws.close = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"error": "Invalid API key"}),
            extra=None,
        )
    )

    client, session = _make_client(ws_mock=ws)

    with pytest.raises(HubbleAuthError):
        await client.async_connect()


async def test_connect_raises_auth_error_on_401_handshake() -> None:
    """async_connect raises HubbleAuthError on HTTP 401 WS handshake."""
    client, session = _make_client()
    session.ws_connect = AsyncMock(
        side_effect=aiohttp.WSServerHandshakeError(
            request_info=MagicMock(), history=(), status=401
        )
    )

    with pytest.raises(HubbleAuthError):
        await client.async_connect()


async def test_connect_raises_connection_error_on_client_error() -> None:
    """async_connect raises HubbleConnectionError on aiohttp.ClientError."""
    client, session = _make_client()
    session.ws_connect = AsyncMock(side_effect=aiohttp.ClientError("boom"))

    with pytest.raises(HubbleConnectionError):
        await client.async_connect()


# ── async_listen ───────────────────────────────────────────────────────────────

async def test_listen_dispatches_text_messages() -> None:
    """async_listen calls on_event for each TEXT message."""
    received = []

    ws = _make_ws([
        _ws_message(
            aiohttp.WSMsgType.TEXT,
            json.dumps({"event": "page:changed", "data": {"activePage": 2}}),
        ),
        _ws_message(
            aiohttp.WSMsgType.TEXT,
            json.dumps({"event": "notification", "data": {"id": "abc"}}),
        ),
        _ws_message(aiohttp.WSMsgType.CLOSED),
    ])

    client, _ = _make_client(ws_mock=ws, on_event=lambda e, d: received.append((e, d)))

    # Manually set the ws so we can call async_listen directly
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )
    await client.async_connect()
    await client.async_listen()

    assert ("page:changed", {"activePage": 2}) in received
    assert ("notification", {"id": "abc"}) in received


async def test_listen_returns_on_clean_close() -> None:
    """async_listen returns normally on WSMsgType.CLOSE."""
    ws = _make_ws([_ws_message(aiohttp.WSMsgType.CLOSE)])
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()
    # Should return without raising
    await client.async_listen()


async def test_listen_raises_on_ws_error() -> None:
    """async_listen raises HubbleConnectionError on WSMsgType.ERROR."""
    ws = _make_ws([_ws_message(aiohttp.WSMsgType.ERROR)])
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()

    with pytest.raises(HubbleConnectionError):
        await client.async_listen()


# ── async_add_subscription ─────────────────────────────────────────────────────

async def test_add_subscription_sends_add_message() -> None:
    """async_add_subscription sends {"action": "add", ...} to the live connection."""
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, _ = _make_client(ws_mock=ws)
    await client.async_connect()
    ws.send_str.reset_mock()  # clear auth + subscribe calls

    await client.async_add_subscription(modules=["hubble-timer"])

    sent = json.loads(ws.send_str.call_args[0][0])
    assert sent["action"] == "add"
    assert "hubble-timer" in sent["modules"]


async def test_add_subscription_updates_internal_state() -> None:
    """async_add_subscription updates _subscriptions so reconnect replays it."""
    ws = MagicMock()
    ws.closed = False
    ws.send_str = AsyncMock()
    ws.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )

    client, session = _make_client(ws_mock=ws)
    await client.async_connect()
    await client.async_add_subscription(modules=["hubble-timer"])

    assert "hubble-timer" in client._subscriptions["modules"]

    # Simulate reconnect: a new ws_connect call should send full subscribe
    ws2 = MagicMock()
    ws2.send_str = AsyncMock()
    ws2.receive = AsyncMock(
        return_value=aiohttp.WSMessage(
            type=aiohttp.WSMsgType.TEXT,
            data=json.dumps({"authenticated": True}),
            extra=None,
        )
    )
    session.ws_connect = AsyncMock(return_value=ws2)
    await client.async_connect()

    # The subscribe message on reconnect must include hubble-timer
    subscribe_call = next(
        json.loads(call[0][0])
        for call in ws2.send_str.call_args_list
        if json.loads(call[0][0]).get("action") == "subscribe"
    )
    assert "hubble-timer" in subscribe_call.get("modules", [])
