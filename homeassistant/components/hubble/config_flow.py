"""Config flow for the Hubble integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HubbleApiClient, HubbleAuthError, HubbleConnectionError
from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default="Hubble"): str,
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Required(CONF_API_KEY): str,
    }
)


class HubbleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Hubble config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
            )
            try:
                client = HubbleApiClient(
                    host=user_input[CONF_HOST],
                    port=user_input[CONF_PORT],
                    api_key=user_input[CONF_API_KEY],
                    session=async_get_clientsession(self.hass),
                )
                await client.async_get_state()
            except HubbleAuthError:
                errors["base"] = "invalid_auth"
            except HubbleConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error connecting to Hubble")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Initiate re-auth on API key invalidation."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-auth: accept a new API key."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = {**reauth_entry.data, **user_input}
            try:
                client = HubbleApiClient(
                    host=reauth_entry.data[CONF_HOST],
                    port=reauth_entry.data[CONF_PORT],
                    api_key=user_input[CONF_API_KEY],
                    session=async_get_clientsession(self.hass),
                )
                await client.async_get_state()
            except HubbleAuthError:
                errors["base"] = "invalid_auth"
            except HubbleConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error re-authenticating with Hubble")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(reauth_entry, data=new_data)
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )
