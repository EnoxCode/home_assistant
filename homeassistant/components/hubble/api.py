"""Hubble API client."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)


class HubbleError(HomeAssistantError):
    """Base exception for Hubble errors."""


class HubbleAuthError(HubbleError):
    """Raised when the API key is invalid (HTTP 401)."""


class HubbleConnectionError(HubbleError):
    """Raised when the Hubble device cannot be reached."""


class HubbleApiClient:
    """Thin HTTP client for the Hubble REST API."""

    def __init__(
        self,
        host: str,
        port: int,
        api_key: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialise the client."""
        self._base_url = f"http://{host}:{port}"
        self._headers = {"x-api-key": api_key}
        self._session = session

    async def async_get_state(self) -> dict[str, Any]:
        """Return the full dashboard state from GET /api/dashboard/state."""
        url = f"{self._base_url}/api/dashboard/state"
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_get_notify_count(self) -> int:
        """Return the number of currently active notifications."""
        url = f"{self._base_url}/api/dashboard/notify/count"
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                data = await response.json()
                try:
                    return data["count"]
                except (KeyError, TypeError) as err:
                    raise HubbleConnectionError(
                        f"Unexpected notify/count response: {data}"
                    ) from err
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_discover(self) -> dict[str, Any]:
        """Return the discovery payload from GET /api/ws/events."""
        url = f"{self._base_url}/api/ws/events"
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_get_modules(self) -> list[dict[str, Any]]:
        """Return the list of installed modules."""
        url = f"{self._base_url}/api/modules/"  # trailing slash required by Hubble API
        try:
            async with self._session.get(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def _async_post(
        self, path: str, payload: dict | None = None
    ) -> dict[str, Any]:
        """POST to a Hubble endpoint and return the JSON response."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.post(
                url, headers=self._headers, json=payload if payload is not None else {}
            ) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def _async_post_nullable(self, path: str) -> dict[str, Any] | None:
        """POST to an endpoint that may return 204 (no content)."""
        url = f"{self._base_url}{path}"
        try:
            async with self._session.post(
                url, headers=self._headers, json={}
            ) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                if response.status == 204:
                    return None
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def _async_delete(self, path: str) -> dict[str, Any]:
        """DELETE a Hubble endpoint and return the JSON response.

        Note: Hubble DELETE endpoints return HTTP 200 with a JSON body
        (e.g. {"success": true}), not 204. response.json() is safe here.
        """
        url = f"{self._base_url}{path}"
        try:
            async with self._session.delete(url, headers=self._headers) as response:
                if response.status == 401:
                    raise HubbleAuthError("Invalid API key")
                response.raise_for_status()
                return await response.json()
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_next_page(self) -> dict[str, Any]:
        """Advance to the next visible page."""
        return await self._async_post("/api/dashboard/next-page")

    async def async_previous_page(self) -> dict[str, Any]:
        """Go to the previous visible page."""
        return await self._async_post("/api/dashboard/previous-page")

    async def async_next_widget(self) -> dict[str, Any] | None:
        """Select the next widget. Returns None if no selectable widgets (HTTP 204)."""
        return await self._async_post_nullable("/api/dashboard/widget/next")

    async def async_previous_widget(self) -> dict[str, Any] | None:
        """Select the previous widget. Returns None if no selectable widgets (HTTP 204)."""
        return await self._async_post_nullable("/api/dashboard/widget/previous")

    async def async_set_active_page(self, page_id: int) -> dict[str, Any]:
        """Set the active page by ID."""
        return await self._async_post("/api/dashboard/active-page", {"pageId": page_id})

    async def async_dismiss_all_notifications(self) -> dict[str, Any]:
        """Dismiss all active notifications."""
        return await self._async_delete("/api/dashboard/notify")

    async def async_refresh_dashboard(self) -> dict[str, Any]:
        """Reload the Electron dashboard window."""
        return await self._async_post("/api/dashboard/refresh")

    async def async_send_notification(
        self,
        title: str,
        message: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a notification overlay to the dashboard."""
        payload = {"title": title, "message": message, **kwargs}
        return await self._async_post("/api/dashboard/notify", payload)

    async def async_dismiss_notification(self, notification_id: str) -> dict[str, Any]:
        """Dismiss a single notification by UUID."""
        return await self._async_delete(f"/api/dashboard/notify/{notification_id}")
