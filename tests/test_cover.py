# tests/test_cover.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from custom_components.ha_hubitat_bridge.cover import HubitatCover

COVER_DEVICE = {
    "id": "40", "name": "Garage Door", "label": "Garage Door",
    "type": "Garage Door", "capabilities": ["GarageDoorControl"],
    "attributes": [{"name": "door", "currentValue": "closed", "dataType": "ENUM"}],
}


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.hubitat_devices = {"40": COVER_DEVICE}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_initially_closed(coordinator):
    cv = HubitatCover(COVER_DEVICE, coordinator)
    assert cv.is_closed is True


async def test_handle_event_open(hass, coordinator):
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    with patch.object(cv, "async_write_ha_state"):
        cv.handle_event("door", "open")
    assert cv.is_closed is False


async def test_open_command(hass, coordinator):
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    with patch.object(cv, "async_write_ha_state"):
        await cv.async_open_cover()
    coordinator.maker_client.send_command.assert_called_once_with("40", "open")


async def test_close_command(hass, coordinator):
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    with patch.object(cv, "async_write_ha_state"):
        await cv.async_close_cover()
    coordinator.maker_client.send_command.assert_called_once_with("40", "close")
