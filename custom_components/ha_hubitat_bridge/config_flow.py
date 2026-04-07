from __future__ import annotations

import logging
import os
from pathlib import Path
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

CONF_ICON_URL = "icon_url"


def _conn_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HUB_URL, default=defaults.get(CONF_HUB_URL, "http://")): str,
            vol.Required(CONF_APP_ID, default=defaults.get(CONF_APP_ID, vol.UNDEFINED)): vol.Coerce(int),
            vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
        }
    )


async def _validate_credentials(hass, user_input: dict) -> dict[str, str]:
    """Validate hub credentials. Returns errors dict (empty = success)."""
    errors: dict[str, str] = {}
    session = async_get_clientsession(hass)
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
    )
    try:
        try:
            await maker.get_devices()
        except aiohttp.ClientResponseError:
            errors[CONF_TOKEN] = "invalid_token"
        except Exception:
            errors[CONF_HUB_URL] = "cannot_connect"
        else:
            if not await web.async_login():
                errors[CONF_PASSWORD] = "invalid_auth"
    finally:
        await web.async_close()
    return errors


class HubitatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _validate_credentials(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Hubitat Bridge", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_conn_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await _validate_credentials(self.hass, user_input)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_conn_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return HubitatBridgeOptionsFlow(config_entry)


class HubitatBridgeOptionsFlow(config_entries.OptionsFlow):

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            icon_url = user_input.get(CONF_ICON_URL, "").strip()
            if icon_url:
                if not await self._download_icon(icon_url):
                    errors[CONF_ICON_URL] = "icon_download_failed"
            else:
                self._restore_default_icon()
            if not errors:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ICON_URL,
                        default=self._entry.options.get(CONF_ICON_URL, ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _download_icon(self, url: str) -> bool:
        """Download an image from url and save it as icon.png in the integration dir."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    _LOGGER.error("Icon download failed: HTTP %s from %s", resp.status, url)
                    return False
                content_type = resp.headers.get("Content-Type", "")
                if not content_type.startswith("image/"):
                    _LOGGER.error("Icon URL did not return an image (Content-Type: %s)", content_type)
                    return False
                data = await resp.read()
        except Exception as exc:
            _LOGGER.error("Icon download error: %s", exc)
            return False

        icon_path = Path(self.hass.config.config_dir) / "custom_components" / DOMAIN / "icon.png"
        try:
            icon_path.write_bytes(data)
            _LOGGER.info("Custom icon saved to %s — restart HA to apply", icon_path)
        except OSError as exc:
            _LOGGER.error("Could not write icon file: %s", exc)
            return False

        return True

    def _restore_default_icon(self) -> None:
        """Restore icon.png from the committed default (icon_default.png)."""
        integration_dir = Path(self.hass.config.config_dir) / "custom_components" / DOMAIN
        default = integration_dir / "icon_default.png"
        icon = integration_dir / "icon.png"
        if default.exists():
            try:
                import shutil
                shutil.copy2(default, icon)
                _LOGGER.info("Default icon restored — restart HA to apply")
            except OSError as exc:
                _LOGGER.error("Could not restore default icon: %s", exc)
