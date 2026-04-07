# tests/test_fan.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from custom_components.ha_hubitat_bridge.fan import HubitatFan

FAN_DEVICE = {
    "id": "60", "name": "Bedroom Fan", "label": "Bedroom Fan",
    "type": "Fan Controller", "capabilities": ["FanControl"],
    "attributes": [
        {"name": "switch", "currentValue": "on", "dataType": "ENUM"},
        {"name": "speed", "currentValue": "medium", "dataType": "ENUM"},
    ],
}


@pytest.fixture
def coordinator():
    c = MagicMock()
    c.hubitat_devices = {"60": FAN_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_fan_is_on(coordinator):
    f = HubitatFan(FAN_DEVICE, coordinator)
    assert f.is_on is True


async def test_handle_event_off(hass, coordinator):
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    with patch.object(f, "async_write_ha_state"):
        f.handle_event("switch", "off")
    assert f.is_on is False


async def test_turn_on(hass, coordinator):
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    with patch.object(f, "async_write_ha_state"):
        await f.async_turn_on()
    coordinator.maker_client.send_command.assert_called_with("60", "on")


async def test_turn_off(hass, coordinator):
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    with patch.object(f, "async_write_ha_state"):
        await f.async_turn_off()
    coordinator.maker_client.send_command.assert_called_with("60", "off")
