"""Hubble WebSocket client."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
from typing import Any

import aiohttp
from aiohttp import WSMsgType

from .api import HubbleAuthError, HubbleConnectionError

_LOGGER = logging.getLogger(__name__)

# Core events subscribed to by default on every connection.
_DEFAULT_EVENTS: frozenset[str] = frozenset(
    {
        "page:changed",
        "notification",
        "notification:dismissed",
        "media:state",
        "screen:changed",
    }
)


class HubbleWebSocketClient:
    """Manage the Hubble WebSocket connection lifecycle.

    Does not retry — the coordinator controls reconnection timing.
    """

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
        on_event: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Initialise the client."""
        self._url = f"ws://{host}:{port}/ws"
        self._api_key = api_key
        self._session = session
        self._on_event = on_event
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        # Accumulated subscription state — replayed as a full subscribe on reconnect.
        self._subscriptions: dict[str, set[str]] = {
            "events": set(_DEFAULT_EVENTS),
            "modules": set(),
            "moduleTopics": set(),
        }

    # ── Public interface ────────────────────────────────────────────────────────

    async def async_connect(self) -> None:
        """Open connection, authenticate, and send initial subscribe."""
        try:
            self._ws = await self._session.ws_connect(self._url)
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise HubbleAuthError(
                    "WebSocket handshake rejected: invalid API key"
                ) from err
            raise HubbleConnectionError(f"WebSocket handshake failed: {err}") from err
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(
                f"Cannot connect to Hubble WebSocket: {err}"
            ) from err

        # Authenticate — close socket on failure so we don't leak it.
        _auth_ok = False
        try:
            await self._ws.send_str(
                json.dumps({"action": "auth", "apiKey": self._api_key})
            )
            msg = await self._ws.receive()
            if msg.type != WSMsgType.TEXT:
                raise HubbleConnectionError(
                    f"Unexpected message type during auth: {msg.type}"
                )
            auth_resp = json.loads(msg.data)
            if "error" in auth_resp:
                raise HubbleAuthError(f"WebSocket auth rejected: {auth_resp['error']}")
            if not auth_resp.get("authenticated"):
                raise HubbleConnectionError(f"Unexpected auth response: {auth_resp}")
            _auth_ok = True
        finally:
            if not _auth_ok:
                await self._ws.close()
                self._ws = None

        # Subscribe using full accumulated subscription state
        assert self._ws is not None  # auth succeeded, socket is open
        await self._ws.send_str(json.dumps(self._build_action_message("subscribe")))

    async def async_listen(self) -> None:
        """Receive loop. Returns on clean close. Raises HubbleConnectionError on error."""
        if self._ws is None:
            raise HubbleConnectionError("Not connected — call async_connect first")
        async for msg in self._ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    parsed = json.loads(msg.data)
                except json.JSONDecodeError:
                    _LOGGER.warning(
                        "Received invalid JSON from Hubble WebSocket: %s", msg.data
                    )
                    continue
                self._on_event(parsed.get("event", ""), parsed.get("data") or {})
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                break
            elif msg.type == WSMsgType.ERROR:
                raise HubbleConnectionError("WebSocket error received")

    async def async_disconnect(self) -> None:
        """Close the connection cleanly."""
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def async_add_subscription(
        self,
        *,
        events: list[str] | None = None,
        modules: list[str] | None = None,
        module_topics: list[str] | None = None,
    ) -> None:
        """Add to the current subscription and send an {"action": "add"} message.

        Updates internal state so reconnects replay the full subscription.
        If not currently connected, state is still updated but no message is sent.
        """
        added: dict[str, list[str]] = {}
        if events:
            self._subscriptions["events"].update(events)
            added["events"] = events
        if modules:
            self._subscriptions["modules"].update(modules)
            added["modules"] = modules
        if module_topics:
            self._subscriptions["moduleTopics"].update(module_topics)
            added["moduleTopics"] = module_topics
        if added and self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps({"action": "add", **added}))

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _build_action_message(self, action: str) -> dict[str, Any]:
        """Build a subscribe/add message from current _subscriptions (omit empty sets)."""
        msg: dict[str, Any] = {"action": action}
        if self._subscriptions["events"]:
            msg["events"] = sorted(self._subscriptions["events"])
        if self._subscriptions["modules"]:
            msg["modules"] = sorted(self._subscriptions["modules"])
        if self._subscriptions["moduleTopics"]:
            msg["moduleTopics"] = sorted(self._subscriptions["moduleTopics"])
        return msg
