from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_cover(device: dict) -> bool:
    return "GarageDoorControl" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatCover(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_cover(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_cover(device):
            async_add_entities([HubitatCover(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatCover(HubitatEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.GARAGE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_closed = self._get_attr("door") == "closed"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "door":
            self._attr_is_closed = value == "closed"
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "open")
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "close")
        self._attr_is_closed = True
        self.async_write_ha_state()
