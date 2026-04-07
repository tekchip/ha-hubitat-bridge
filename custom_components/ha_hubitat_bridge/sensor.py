from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, PERCENTAGE, LIGHT_LUX
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _sensor_entities(device: dict, coordinator: HubitatCoordinator) -> list:
    caps = device.get("capabilities", [])
    entities = []
    if "TemperatureMeasurement" in caps:
        entities.append(HubitatTemperatureSensor(device, coordinator))
    if "RelativeHumidityMeasurement" in caps:
        entities.append(HubitatHumiditySensor(device, coordinator))
    if "IlluminanceMeasurement" in caps:
        entities.append(HubitatIlluminanceSensor(device, coordinator))
    if "PowerMeter" in caps:
        entities.append(HubitatPowerSensor(device, coordinator))
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for d in coordinator.hubitat_devices.values():
        entities.extend(_sensor_entities(d, coordinator))
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        new = _sensor_entities(device, coordinator)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class _HubitatNumericSensor(HubitatEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _hubitat_attribute: str = ""

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        raw = self._get_attr(self._hubitat_attribute)
        self._attr_native_value = float(raw) if raw is not None else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == self._hubitat_attribute:
            try:
                self._attr_native_value = float(value)
            except ValueError:
                pass
            self.async_write_ha_state()


class HubitatTemperatureSensor(_HubitatNumericSensor):
    _hubitat_attribute = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_temperature"


class HubitatHumiditySensor(_HubitatNumericSensor):
    _hubitat_attribute = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_humidity"


class HubitatIlluminanceSensor(_HubitatNumericSensor):
    _hubitat_attribute = "illuminance"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_illuminance"


class HubitatPowerSensor(_HubitatNumericSensor):
    _hubitat_attribute = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_power"
