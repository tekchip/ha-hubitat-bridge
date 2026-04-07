from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_APP_ID,
    CONF_HUB_URL,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)
from .hubitat_client import HubitatMakerClient, HubitatWebClient

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HUB_URL, default="http://"): str,
        vol.Required(CONF_APP_ID): vol.Coerce(int),
        vol.Required(CONF_TOKEN): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HubitatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            maker = HubitatMakerClient(
                user_input[CONF_HUB_URL],
                user_input[CONF_APP_ID],
                user_input[CONF_TOKEN],
                session,
            )
            web = HubitatWebClient(
                user_input[CONF_HUB_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                session,
            )

            try:
                await maker.get_devices()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                ok = await web.async_login()
                if not ok:
                    errors["base"] = "invalid_auth"

            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Hubitat Bridge", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
        )
