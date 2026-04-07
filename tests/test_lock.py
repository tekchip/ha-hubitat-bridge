# tests/test_lock.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from custom_components.ha_hubitat_bridge.lock import HubitatLock

LOCK_DEVICE = {
    "id": "30", "name": "Front Lock", "label": "Front Lock",
    "type": "Z-Wave Lock", "capabilities": ["Lock"],
    "attributes": [{"name": "lock", "currentValue": "locked", "dataType": "ENUM"}],
}


@pytest.fixture
def coordinator():
    coord = MagicMock()
    coord.hubitat_devices = {"30": LOCK_DEVICE}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_initially_locked(coordinator):
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    assert lk.is_locked is True


async def test_handle_event_unlocked(hass, coordinator):
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    with patch.object(lk, "async_write_ha_state"):
        lk.handle_event("lock", "unlocked")
    assert lk.is_locked is False


async def test_lock_command(hass, coordinator):
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    with patch.object(lk, "async_write_ha_state"):
        await lk.async_lock()
    coordinator.maker_client.send_command.assert_called_once_with("30", "lock")


async def test_unlock_command(hass, coordinator):
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    with patch.object(lk, "async_write_ha_state"):
        await lk.async_unlock()
    coordinator.maker_client.send_command.assert_called_once_with("30", "unlock")
