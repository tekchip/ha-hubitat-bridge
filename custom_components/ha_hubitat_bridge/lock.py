from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_lock(device: dict) -> bool:
    return "Lock" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatLock(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_lock(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_lock(device):
            async_add_entities([HubitatLock(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatLock(HubitatEntity, LockEntity):
    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_locked = self._get_attr("lock") == "locked"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "lock":
            self._attr_is_locked = value == "locked"
            self.async_write_ha_state()

    async def async_lock(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "lock")
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "unlock")
        self._attr_is_locked = False
        self.async_write_ha_state()
