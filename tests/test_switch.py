# tests/test_switch.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_hubitat_bridge.switch import HubitatSwitch, _is_switch

DEVICE = {
    "id": "1",
    "name": "Living Room Switch",
    "label": "Living Room Switch",
    "type": "Generic Zigbee Switch",
    "capabilities": ["Switch"],
    "attributes": [{"name": "switch", "currentValue": "on", "dataType": "ENUM"}],
}


@pytest.fixture
def mock_coordinator():
    coord = MagicMock()
    coord.hubitat_devices = {"1": DEVICE}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_switch_is_on(mock_coordinator):
    sw = HubitatSwitch(DEVICE, mock_coordinator)
    assert sw.is_on is True


async def test_switch_is_off_when_attribute_off():
    device = {**DEVICE, "attributes": [{"name": "switch", "currentValue": "off", "dataType": "ENUM"}]}
    coord = MagicMock()
    coord.maker_client = AsyncMock()
    sw = HubitatSwitch(device, coord)
    assert sw.is_on is False


async def test_handle_event_updates_state(hass, mock_coordinator):
    sw = HubitatSwitch(DEVICE, mock_coordinator)
    sw.hass = hass
    with patch.object(sw, "async_write_ha_state"):
        sw.handle_event("switch", "off")
    assert sw.is_on is False


async def test_turn_on_sends_command(hass, mock_coordinator):
    sw = HubitatSwitch(DEVICE, mock_coordinator)
    sw.hass = hass
    with patch.object(sw, "async_write_ha_state"):
        await sw.async_turn_on()
    mock_coordinator.maker_client.send_command.assert_called_once_with("1", "on")


async def test_turn_off_sends_command(hass, mock_coordinator):
    sw = HubitatSwitch(DEVICE, mock_coordinator)
    sw.hass = hass
    with patch.object(sw, "async_write_ha_state"):
        await sw.async_turn_off()
    mock_coordinator.maker_client.send_command.assert_called_once_with("1", "off")


async def test_dimmer_excluded_from_switch(mock_coordinator):
    """Devices with SwitchLevel should not be HubitatSwitch entities."""
    dimmer = {**DEVICE, "capabilities": ["Switch", "SwitchLevel"]}
    assert _is_switch(dimmer) is False
    assert _is_switch(DEVICE) is True
