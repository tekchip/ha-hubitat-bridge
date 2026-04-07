from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entity_map import EntityMap
from .hubitat_client import HubitatMakerClient, HubitatWebClient


class HAToHubitat:
    """Stub — fully implemented in Task 16."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        maker_client: HubitatMakerClient,
        web_client: HubitatWebClient,
        entity_map: EntityMap,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._maker_client = maker_client
        self._web_client = web_client
        self._entity_map = entity_map
        self._unsub = None

    async def async_setup(self) -> None:
        pass

    async def async_teardown(self) -> None:
        if self._unsub:
            self._unsub()
