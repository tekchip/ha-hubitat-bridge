# tests/test_light.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from custom_components.ha_hubitat_bridge.light import HubitatLight

DIMMER = {
    "id": "2",
    "name": "Bedroom Light",
    "label": "Bedroom Light",
    "type": "Generic Zigbee Dimmer",
    "capabilities": ["Switch", "SwitchLevel"],
    "attributes": [
        {"name": "switch", "currentValue": "on", "dataType": "ENUM"},
        {"name": "level", "currentValue": 80, "dataType": "NUMBER"},
    ],
}


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.hubitat_devices = {"2": DIMMER}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_light_is_on(coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    assert lt.is_on is True


async def test_light_brightness_scaled(coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    # Hubitat 0-100 → HA 0-255
    assert lt.brightness == int(80 / 100 * 255)


async def test_handle_event_switch(hass, coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    with patch.object(lt, "async_write_ha_state"):
        lt.handle_event("switch", "off")
    assert lt.is_on is False


async def test_handle_event_level(hass, coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    with patch.object(lt, "async_write_ha_state"):
        lt.handle_event("level", "50")
    assert lt.brightness == int(50 / 100 * 255)


async def test_turn_on_with_brightness(hass, coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    with patch.object(lt, "async_write_ha_state"):
        await lt.async_turn_on(brightness=128)
    # 128/255*100 ≈ 50
    coordinator.maker_client.send_command.assert_any_call("2", "setLevel", "50")


async def test_turn_on_no_brightness(hass, coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    with patch.object(lt, "async_write_ha_state"):
        await lt.async_turn_on()
    coordinator.maker_client.send_command.assert_any_call("2", "on")


async def test_turn_off(hass, coordinator):
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    with patch.object(lt, "async_write_ha_state"):
        await lt.async_turn_off()
    coordinator.maker_client.send_command.assert_called_once_with("2", "off")
