"""DataUpdateCoordinator for Hubble."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.helpers.entity import Entity

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError, HubbleError
from .const import (
    CONF_SCREEN_POLL_INTERVAL,
    CONF_SCREEN_STATUS_COMMAND,
    DEFAULT_SCREEN_POLL_INTERVAL,
    DEFAULT_SCREEN_STATUS_COMMAND,
    DOMAIN,
    SCAN_INTERVAL,
)
from .websocket import HubbleWebSocketClient

_LOGGER = logging.getLogger(__name__)

type HubbleConfigEntry = ConfigEntry[HubbleCoordinator]


class HubbleScreenCoordinator(DataUpdateCoordinator[bool | None]):
    """Poll screen-status command and cache the result as a bool."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HubbleConfigEntry,
        client: HubbleApiClient,
    ) -> None:
        """Initialise the screen coordinator."""
        poll_interval = entry.data.get(
            CONF_SCREEN_POLL_INTERVAL, DEFAULT_SCREEN_POLL_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_screen",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client
        self._status_slug: str = entry.data.get(
            CONF_SCREEN_STATUS_COMMAND, DEFAULT_SCREEN_STATUS_COMMAND
        )

    async def _async_update_data(self) -> bool | None:
        """Fetch screen state by executing the screen-status command."""
        try:
            result = await self.client.async_execute_command(self._status_slug)
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return result.get("stdout", "").strip().lower() == "true"


class HubbleCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and cache Hubble dashboard state."""

    config_entry: HubbleConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HubbleConfigEntry,
        client: HubbleApiClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        # Set by async_setup_entry before first refresh.
        self.discovery: dict[str, Any] = {}
        # WebSocket client and reconnect task.
        self.ws_client: HubbleWebSocketClient | None = None
        self._ws_reconnect_task: asyncio.Task | None = None
        # Module event handlers: (module_name, topic) -> handler.
        self._module_handlers: dict[
            tuple[str, str], Callable[[dict[str, Any]], None]
        ] = {}
        # Core event handlers registered by platform entities (e.g. media player).
        self._core_handlers: dict[str, Callable[[dict[str, Any]], None]] = {}
        # Pending WS module subscriptions — populated by platform setup before WS opens.
        self._pending_module_subs: set[str] = set()
        # Media player state shared between select and media_player platforms.
        self.media_state: dict[str, Any] | None = None
        # References to the media player and display mode entities for WS updates.
        self.media_player_entity: Entity | None = None
        self.display_mode_entity: Entity | None = None
        # Reference to the active widget select entity for WS-driven option rebuilds.
        self.active_widget_entity: Entity | None = None
        # Screen coordinator — set by async_setup_entry after creation.
        self.screen_coordinator: HubbleScreenCoordinator | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest state from Hubble REST endpoints (fallback resync)."""
        try:
            state, notify_count = await asyncio.gather(
                self.client.async_get_state(),
                self.client.async_get_notify_count(),
            )
        except HubbleAuthError as err:
            raise ConfigEntryAuthFailed from err
        except HubbleConnectionError as err:
            raise UpdateFailed(str(err)) from err
        return {**state, "notificationCount": notify_count}

    # ── Module infrastructure ───────────────────────────────────────────────────

    def is_module_discovered(self, module_name: str) -> bool:
        """Return True if module_name is present in discovery data."""
        return any(
            m["module"] == module_name for m in self.discovery.get("modules", [])
        )

    def add_pending_module_subscription(self, module_name: str) -> None:
        """Queue a module WS subscription to be applied when the socket opens.

        This indirection is needed because platform setup (sensor.py) runs before
        async_start_websocket is called, so ws_client is None at that point.
        async_start_websocket reads _pending_module_subs and transfers them to the
        newly-created ws_client before starting the reconnect loop.
        """
        self._pending_module_subs.add(module_name)

    def register_module_handler(
        self,
        module_name: str,
        topic: str,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a callback for a specific module:data event.

        Future module platforms (e.g. hubble-timer) call this in their
        async_setup_entry after verifying is_module_discovered().
        """
        self._module_handlers[(module_name, topic)] = handler

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

    # ── WebSocket event routing ─────────────────────────────────────────────────

    def _handle_ws_event(self, event: str, data: dict[str, Any]) -> None:
        """Route an incoming WebSocket event to the correct handler."""
        if event == "module:data":
            module = data.get("module", "")
            topic = data.get("topic", "")
            handler = self._module_handlers.get((module, topic))
            if handler:
                handler(data.get("data") or {})
            else:
                _LOGGER.debug("Unhandled module:data event: %s:%s", module, topic)
            return

        # Core handler registry — checked before the match block.
        handler = self._core_handlers.get(event)
        if handler:
            handler(data)
            return

        # screen:changed — schedule an immediate screen status poll.
        if event == "screen:changed":
            if self.screen_coordinator is not None:
                self.hass.async_create_task(
                    self.screen_coordinator.async_request_refresh()
                )
            return

        # widget:added / widget:removed — selectable widget list may have changed.
        if event in ("widget:added", "widget:removed"):
            self.hass.async_create_task(self._async_refresh_discovery())
            return

        # Core events — patch coordinator data in place.
        current = dict(self.data) if self.data else {}
        match event:
            case "page:changed":
                # Only update activePage and widgets.
                # Do NOT replace the pages list — the WS payload only sends a
                # single page object, not the full list. Replacing pages would
                # break HubbleCurrentPageSensor which iterates coordinator.data["pages"].
                current["activePage"] = data.get(
                    "activePage", current.get("activePage")
                )
                if "widgets" in data:
                    current["widgets"] = data["widgets"]
            case "notification":
                current["notificationCount"] = current.get("notificationCount", 0) + 1
            case "notification:dismissed":
                current["notificationCount"] = max(
                    0, current.get("notificationCount", 0) - 1
                )
            case _:
                _LOGGER.debug("Unhandled core WebSocket event: %s", event)
                return
        self.async_set_updated_data(current)

    async def _async_refresh_discovery(self) -> None:
        """Re-fetch discovery and notify the active widget entity of option changes."""
        try:
            self.discovery = await self.client.async_discover()
        except HubbleError:
            _LOGGER.error("Failed to refresh Hubble discovery data")
            return
        if self.active_widget_entity is not None:
            self.active_widget_entity.async_write_ha_state()

    # ── WebSocket lifecycle ─────────────────────────────────────────────────────

    async def async_start_websocket(self) -> None:
        """Create WebSocket client and start the reconnect loop."""
        self.ws_client = HubbleWebSocketClient(
            host=self.config_entry.data[CONF_HOST],
            port=self.config_entry.data[CONF_PORT],
            api_key=self.config_entry.data[CONF_API_KEY],
            session=async_get_clientsession(self.hass),
            on_event=self._handle_ws_event,
        )
        # Transfer pending module subscriptions to the ws_client. Since _ws is None
        # at this point, async_add_subscription only updates internal subscription
        # state (no I/O). The updated state is included in the subscribe message
        # sent by async_connect on the first reconnect loop iteration.
        if self._pending_module_subs:
            await self.ws_client.async_add_subscription(
                modules=list(self._pending_module_subs)
            )
            self._pending_module_subs.clear()
        self._ws_reconnect_task = self.hass.async_create_task(
            self._ws_reconnect_loop(),
            eager_start=False,
        )

    async def async_stop_websocket(self) -> None:
        """Cancel reconnect task and close WebSocket connection.

        Shutdown sequence:
          1. Cancel the reconnect task.
          2. Await it so CancelledError propagates cleanly.
          3. Disconnect the underlying ws connection.
        """
        if self._ws_reconnect_task is not None:
            self._ws_reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_reconnect_task
            self._ws_reconnect_task = None
        if self.ws_client is not None:
            await self.ws_client.async_disconnect()
            self.ws_client = None

    async def _ws_reconnect_loop(self) -> None:
        """Connect and listen. Retry with exponential backoff on failure.

        Clean close (listen returns normally) → reconnect after backoff.
        HubbleAuthError → trigger re-auth and exit — do not retry.
        HubbleConnectionError → retry after backoff.
        CancelledError → exit cleanly.
        """
        assert self.ws_client is not None  # always set before this task starts
        backoff = 1
        while True:
            try:
                await self.ws_client.async_connect()
                backoff = 1  # reset on successful connect
                await self.ws_client.async_listen()
                # listen returned normally (clean close) — fall through to reconnect
            except HubbleAuthError:
                self.config_entry.async_start_reauth(self.hass)
                return
            except HubbleConnectionError:
                pass  # retry after backoff
            except asyncio.CancelledError:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
