from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity

_SPEED_TO_PCT = {"low": 33, "medium-low": 50, "medium": 66, "high": 100}
_PCT_TO_SPEED = {33: "low", 50: "medium-low", 66: "medium", 100: "high"}


def _is_fan(device: dict) -> bool:
    return "FanControl" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatFan(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_fan(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_fan(device):
            async_add_entities([HubitatFan(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatFan(HubitatEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"
        speed = self._get_attr("speed")
        self._attr_percentage = _SPEED_TO_PCT.get(speed, 0) if speed else 0

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            if value == "on":
                # If turning on, restore to non-zero percentage or default to medium
                if self._attr_percentage == 0:
                    self._attr_percentage = _SPEED_TO_PCT["medium"]
            else:
                # If turning off, set percentage to 0
                self._attr_percentage = 0
        elif attribute == "speed":
            self._attr_percentage = _SPEED_TO_PCT.get(value, 0)
        self.async_write_ha_state()

    async def async_turn_on(self, percentage: int | None = None, **kwargs) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._coordinator.maker_client.send_command(self._device_id, "on")
            # Set to medium speed if turning on without a specific percentage
            if self._attr_percentage == 0:
                self._attr_percentage = _SPEED_TO_PCT["medium"]
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_percentage = 0
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        speed = min(_PCT_TO_SPEED, key=lambda p: abs(p - percentage))
        await self._coordinator.maker_client.send_command(self._device_id, "setSpeed", _PCT_TO_SPEED[speed])
        self._attr_percentage = percentage
        self.async_write_ha_state()
