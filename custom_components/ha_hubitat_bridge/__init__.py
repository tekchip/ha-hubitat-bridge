from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_APP_ID, CONF_HUB_URL, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, DOMAIN, PLATFORMS
from .entity_map import EntityMap
from .ha_to_hubitat import HAToHubitat
from .hubitat_client import HubitatMakerClient, HubitatWebClient
from .hubitat_to_ha import HubitatCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    maker_client = HubitatMakerClient(
        entry.data[CONF_HUB_URL],
        entry.data[CONF_APP_ID],
        entry.data[CONF_TOKEN],
        session,
    )
    web_client = HubitatWebClient(
        entry.data[CONF_HUB_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    entry.async_on_unload(web_client.async_close)
    entity_map = EntityMap(hass)
    await entity_map.async_load()

    coordinator = HubitatCoordinator(hass, entry, maker_client)
    ha_to_hubitat = HAToHubitat(hass, entry, maker_client, web_client, entity_map)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "ha_to_hubitat": ha_to_hubitat,
    }

    await coordinator.async_setup()
    await ha_to_hubitat.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, {})
    return unload_ok
