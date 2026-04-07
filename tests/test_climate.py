# tests/test_climate.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.components.climate import HVACMode
from custom_components.ha_hubitat_bridge.climate import HubitatClimate

CLIMATE_DEVICE = {
    "id": "50", "name": "Hallway Thermostat", "label": "Hallway Thermostat",
    "type": "Z-Wave Thermostat", "capabilities": ["Thermostat"],
    "attributes": [
        {"name": "thermostatMode", "currentValue": "cool", "dataType": "ENUM"},
        {"name": "temperature", "currentValue": 22.0, "dataType": "NUMBER"},
        {"name": "coolingSetpoint", "currentValue": 24.0, "dataType": "NUMBER"},
        {"name": "heatingSetpoint", "currentValue": 19.0, "dataType": "NUMBER"},
    ],
}


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.hubitat_devices = {"50": CLIMATE_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_hvac_mode(coordinator):
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    assert cl.hvac_mode == HVACMode.COOL


async def test_current_temperature(coordinator):
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    assert cl.current_temperature == 22.0


async def test_handle_event_mode(hass, coordinator):
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    with patch.object(cl, "async_write_ha_state"):
        cl.handle_event("thermostatMode", "heat")
    assert cl.hvac_mode == HVACMode.HEAT


async def test_set_hvac_mode(hass, coordinator):
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    with patch.object(cl, "async_write_ha_state"):
        await cl.async_set_hvac_mode(HVACMode.OFF)
    coordinator.maker_client.send_command.assert_called_once_with("50", "setThermostatMode", "off")


async def test_set_temperature(hass, coordinator):
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    with patch.object(cl, "async_write_ha_state"):
        await cl.async_set_temperature(temperature=25.0)
    coordinator.maker_client.send_command.assert_any_call("50", "setCoolingSetpoint", "25.0")
