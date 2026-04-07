from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_STORAGE_VERSION = 1
_STORAGE_KEY = f"{DOMAIN}.entity_map"


class EntityMap:
    """Persistent mapping between HA entity_id and Hubitat device ID."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._data: dict[str, str] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = stored or {}

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    def put(self, entity_id: str, hubitat_device_id: str) -> None:
        self._data[entity_id] = hubitat_device_id

    def get(self, entity_id: str) -> str | None:
        return self._data.get(entity_id)

    def has(self, entity_id: str) -> bool:
        return entity_id in self._data

    def all_entity_ids(self) -> list[str]:
        return list(self._data.keys())
