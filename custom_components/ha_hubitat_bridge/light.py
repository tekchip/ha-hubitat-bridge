from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_light(device: dict) -> bool:
    return "SwitchLevel" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatLight(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_light(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_light(device):
            async_add_entities([HubitatLight(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatLight(HubitatEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"
        level = self._get_attr("level")
        self._attr_brightness = int(float(level) / 100 * 255) if level is not None else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            self._attr_is_on = value == "on"
        elif attribute == "level":
            self._attr_brightness = int(float(value) / 100 * 255)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            level = str(round(kwargs[ATTR_BRIGHTNESS] / 255 * 100))
            await self._coordinator.maker_client.send_command(self._device_id, "setLevel", level)
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        else:
            await self._coordinator.maker_client.send_command(self._device_id, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_is_on = False
        self.async_write_ha_state()
