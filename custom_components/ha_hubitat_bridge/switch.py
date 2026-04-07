from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_switch(device: dict) -> bool:
    caps = device.get("capabilities", [])
    return "Switch" in caps and "SwitchLevel" not in caps


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatSwitch(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_switch(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_switch(device):
            async_add_entities([HubitatSwitch(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatSwitch(HubitatEntity, SwitchEntity):
    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            self._attr_is_on = value == "on"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_is_on = False
        self.async_write_ha_state()
