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
                return data["count"]
        except HubbleError:
            raise
        except aiohttp.ClientError as err:
            raise HubbleConnectionError(f"Cannot connect to Hubble: {err}") from err

    async def async_get_modules(self) -> list[dict[str, Any]]:
        """Return the list of installed modules."""
        url = f"{self._base_url}/api/modules/"
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
