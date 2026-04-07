from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity

_HUBITAT_TO_HA_MODE = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "auto": HVACMode.HEAT_COOL,
    "off": HVACMode.OFF,
    "emergency heat": HVACMode.HEAT,
}
_HA_TO_HUBITAT_MODE = {v: k for k, v in _HUBITAT_TO_HA_MODE.items() if k != "emergency heat"}


def _is_climate(device: dict) -> bool:
    return "Thermostat" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatClimate(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_climate(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_climate(device):
            async_add_entities([HubitatClimate(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatClimate(HubitatEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        raw_mode = self._get_attr("thermostatMode") or "off"
        self._attr_hvac_mode = _HUBITAT_TO_HA_MODE.get(raw_mode, HVACMode.OFF)
        temp = self._get_attr("temperature")
        self._attr_current_temperature = float(temp) if temp else None
        cool = self._get_attr("coolingSetpoint")
        heat = self._get_attr("heatingSetpoint")
        self._attr_target_temperature_high = float(cool) if cool else None
        self._attr_target_temperature_low = float(heat) if heat else None
        self._attr_target_temperature = float(cool) if cool else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "thermostatMode":
            self._attr_hvac_mode = _HUBITAT_TO_HA_MODE.get(value, HVACMode.OFF)
        elif attribute == "temperature":
            self._attr_current_temperature = float(value)
        elif attribute == "coolingSetpoint":
            self._attr_target_temperature_high = float(value)
            self._attr_target_temperature = float(value)
        elif attribute == "heatingSetpoint":
            self._attr_target_temperature_low = float(value)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        hubitat_mode = _HA_TO_HUBITAT_MODE.get(hvac_mode, "off")
        await self._coordinator.maker_client.send_command(self._device_id, "setThermostatMode", hubitat_mode)
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        if temp is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setCoolingSetpoint", str(temp))
            self._attr_target_temperature = temp
        if high is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setCoolingSetpoint", str(high))
            self._attr_target_temperature_high = high
        if low is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setHeatingSetpoint", str(low))
            self._attr_target_temperature_low = low
        self.async_write_ha_state()
