# tests/test_sensor.py
from unittest.mock import MagicMock, patch
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from custom_components.ha_hubitat_bridge.sensor import (
    HubitatTemperatureSensor,
    HubitatHumiditySensor,
    HubitatIlluminanceSensor,
    HubitatPowerSensor,
)
from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator

TEMP_DEVICE = {
    "id": "20", "name": "Hallway Temp", "label": "Hallway Temp",
    "type": "Temp Sensor", "capabilities": ["TemperatureMeasurement"],
    "attributes": [{"name": "temperature", "currentValue": 21.5, "dataType": "NUMBER"}],
}
HUMIDITY_DEVICE = {
    "id": "21", "name": "Bath Humidity", "label": "Bath Humidity",
    "type": "Humidity Sensor", "capabilities": ["RelativeHumidityMeasurement"],
    "attributes": [{"name": "humidity", "currentValue": 65.0, "dataType": "NUMBER"}],
}
LUX_DEVICE = {
    "id": "22", "name": "Living Lux", "label": "Living Lux",
    "type": "Lux Sensor", "capabilities": ["IlluminanceMeasurement"],
    "attributes": [{"name": "illuminance", "currentValue": 300, "dataType": "NUMBER"}],
}
POWER_DEVICE = {
    "id": "23", "name": "Plug Power", "label": "Plug Power",
    "type": "Power Meter", "capabilities": ["PowerMeter"],
    "attributes": [{"name": "power", "currentValue": 45.2, "dataType": "NUMBER"}],
}


def make_coord(hass, device):
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {device["id"]: device}
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_temperature_value(hass):
    s = HubitatTemperatureSensor(TEMP_DEVICE, make_coord(hass, TEMP_DEVICE))
    assert s.native_value == 21.5
    assert s.device_class == SensorDeviceClass.TEMPERATURE


async def test_humidity_value(hass):
    s = HubitatHumiditySensor(HUMIDITY_DEVICE, make_coord(hass, HUMIDITY_DEVICE))
    assert s.native_value == 65.0


async def test_illuminance_value(hass):
    s = HubitatIlluminanceSensor(LUX_DEVICE, make_coord(hass, LUX_DEVICE))
    assert s.native_value == 300.0


async def test_power_value(hass):
    s = HubitatPowerSensor(POWER_DEVICE, make_coord(hass, POWER_DEVICE))
    assert s.native_value == 45.2


async def test_handle_event_temperature(hass):
    s = HubitatTemperatureSensor(TEMP_DEVICE, make_coord(hass, TEMP_DEVICE))
    s.hass = hass
    with patch.object(s, "async_write_ha_state"):
        s.handle_event("temperature", "22.1")
    assert s.native_value == 22.1
