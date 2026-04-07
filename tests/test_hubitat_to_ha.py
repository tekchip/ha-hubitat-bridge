# tests/test_hubitat_to_ha.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator

DEVICE_SWITCH = {
    "id": "1",
    "name": "Living Room Switch",
    "label": "Living Room Switch",
    "type": "Generic Zigbee Switch",
    "capabilities": ["Switch"],
    "attributes": [{"name": "switch", "currentValue": "on", "dataType": "ENUM"}],
}

DEVICE_DIMMER = {
    "id": "2",
    "name": "Bedroom Light",
    "label": "Bedroom Light",
    "type": "Generic Zigbee Light",
    "capabilities": ["Switch", "SwitchLevel"],
    "attributes": [
        {"name": "switch", "currentValue": "on", "dataType": "ENUM"},
        {"name": "level", "currentValue": 80, "dataType": "NUMBER"},
    ],
}


@pytest.fixture
def mock_maker_client():
    client = AsyncMock()
    client.get_devices = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
    client.get_device = AsyncMock(side_effect=lambda did: DEVICE_SWITCH if did == "1" else DEVICE_DIMMER)
    client.subscribe_url = AsyncMock(return_value={"result": "ok"})
    return client


@pytest.fixture
def mock_entry():
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.async_on_unload = MagicMock(return_value=lambda: None)
    return entry


async def test_async_setup_fetches_devices(hass: HomeAssistant, mock_maker_client, mock_entry):
    with patch("custom_components.ha_hubitat_bridge.hubitat_to_ha.webhook_register"):
        coordinator = HubitatCoordinator(hass, mock_entry, mock_maker_client)
        await coordinator.async_setup()
    assert "1" in coordinator.hubitat_devices
    assert "2" in coordinator.hubitat_devices


async def test_webhook_event_dispatches_to_entity(hass: HomeAssistant, mock_maker_client, mock_entry):
    with patch("custom_components.ha_hubitat_bridge.hubitat_to_ha.webhook_register"):
        coordinator = HubitatCoordinator(hass, mock_entry, mock_maker_client)
        await coordinator.async_setup()

    mock_entity = MagicMock()
    coordinator.register_entity("1", mock_entity)

    # Simulate a webhook event
    mock_request = AsyncMock()
    mock_request.json = AsyncMock(return_value={"content": {"deviceId": "1", "name": "switch", "value": "off"}})
    await coordinator._handle_webhook(hass, "wh_id", mock_request)

    mock_entity.handle_event.assert_called_once_with("switch", "off")


async def test_new_device_on_poll_sends_signal(hass: HomeAssistant, mock_maker_client, mock_entry):
    with patch("custom_components.ha_hubitat_bridge.hubitat_to_ha.webhook_register"):
        coordinator = HubitatCoordinator(hass, mock_entry, mock_maker_client)
        await coordinator.async_setup()

    # Add a new device to mock
    DEVICE_NEW = {
        "id": "3",
        "name": "New Sensor",
        "label": "New Sensor",
        "type": "Contact Sensor",
        "capabilities": ["ContactSensor"],
        "attributes": [{"name": "contact", "currentValue": "closed", "dataType": "ENUM"}],
    }
    mock_maker_client.get_devices = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}, {"id": "3"}])
    mock_maker_client.get_device = AsyncMock(
        side_effect=lambda did: DEVICE_SWITCH if did == "1" else (DEVICE_DIMMER if did == "2" else DEVICE_NEW)
    )

    signals = []
    from homeassistant.helpers.dispatcher import async_dispatcher_connect
    from custom_components.ha_hubitat_bridge.const import SIGNAL_NEW_DEVICE
    async_dispatcher_connect(
        hass, SIGNAL_NEW_DEVICE.format(entry_id="test_entry_id"), lambda d: signals.append(d)
    )

    await coordinator._async_poll(None)
    await hass.async_block_till_done()
    assert any(d["id"] == "3" for d in signals)
