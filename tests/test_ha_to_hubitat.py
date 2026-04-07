# tests/test_ha_to_hubitat.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.const import EntityCategory

from custom_components.ha_hubitat_bridge.entity_map import EntityMap
from custom_components.ha_hubitat_bridge.ha_to_hubitat import HAToHubitat


@pytest.fixture
def maker_client():
    c = AsyncMock()
    c.send_command = AsyncMock(return_value={"result": "ok"})
    return c


@pytest.fixture
def web_client():
    c = AsyncMock()
    c.async_create_virtual_device = AsyncMock(return_value="99")
    return c


@pytest.fixture
async def entity_map(hass):
    em = EntityMap(hass)
    await em.async_load()
    return em


@pytest.fixture
def mock_entry():
    e = MagicMock()
    e.entry_id = "test_entry"
    e.async_on_unload = MagicMock(return_value=lambda: None)
    return e


async def test_qualifies_switch(hass, maker_client, web_client, entity_map, mock_entry):
    from custom_components.ha_hubitat_bridge.ha_to_hubitat import _qualifies

    er_entry = MagicMock()
    er_entry.entity_category = None
    er_entry.platform = "zha"
    er_entry.labels = set()

    assert _qualifies("switch.my_switch", er_entry) is True


async def test_qualifies_rejects_hubitat_platform(hass, maker_client, web_client, entity_map, mock_entry):
    from custom_components.ha_hubitat_bridge.ha_to_hubitat import _qualifies

    er_entry = MagicMock()
    er_entry.entity_category = None
    er_entry.platform = "ha_hubitat_bridge"
    er_entry.labels = set()

    assert _qualifies("switch.hubitat_switch", er_entry) is False


async def test_qualifies_rejects_diagnostic(hass, maker_client, web_client, entity_map, mock_entry):
    from custom_components.ha_hubitat_bridge.ha_to_hubitat import _qualifies

    er_entry = MagicMock()
    er_entry.entity_category = EntityCategory.DIAGNOSTIC
    er_entry.platform = "zha"
    er_entry.labels = set()

    assert _qualifies("sensor.signal_strength", er_entry) is False


async def test_qualifies_rejects_ignore_label(hass, maker_client, web_client, entity_map, mock_entry):
    from custom_components.ha_hubitat_bridge.ha_to_hubitat import _qualifies

    er_entry = MagicMock()
    er_entry.entity_category = None
    er_entry.platform = "zha"
    er_entry.labels = {"hubitat-ignore"}

    assert _qualifies("switch.ignored", er_entry) is False


async def test_qualifies_rejects_non_mirror_domain(hass, maker_client, web_client, entity_map, mock_entry):
    from custom_components.ha_hubitat_bridge.ha_to_hubitat import _qualifies

    er_entry = MagicMock()
    er_entry.entity_category = None
    er_entry.platform = "zha"
    er_entry.labels = set()

    assert _qualifies("automation.my_auto", er_entry) is False


async def test_state_change_creates_virtual_device_and_syncs(hass, maker_client, web_client, entity_map, mock_entry):
    """On first state_changed for a qualifying entity, creates virtual device and syncs command."""
    ha_to_hub = HAToHubitat(hass, mock_entry, maker_client, web_client, entity_map)

    er_entry = MagicMock()
    er_entry.entity_category = None
    er_entry.platform = "zha"
    er_entry.labels = set()

    state = MagicMock()
    state.state = "on"
    state.domain = "switch"
    state.attributes = {"friendly_name": "My Switch"}

    with patch("custom_components.ha_hubitat_bridge.ha_to_hubitat.er.async_get") as mock_er:
        mock_er.return_value.async_get = MagicMock(return_value=er_entry)
        await ha_to_hub._handle_state_changed("switch.my_switch", state)

    web_client.async_create_virtual_device.assert_called_once_with("My Switch", "Virtual Switch")
    maker_client.send_command.assert_called_once_with("99", "on")
    assert entity_map.get("switch.my_switch") == "99"


async def test_state_change_syncs_existing_device(hass, maker_client, web_client, entity_map, mock_entry):
    """On state_changed for an already-mapped entity, syncs command without creating a new device."""
    entity_map.put("switch.existing", "42")
    ha_to_hub = HAToHubitat(hass, mock_entry, maker_client, web_client, entity_map)

    state = MagicMock()
    state.state = "off"
    state.domain = "switch"
    state.attributes = {}

    await ha_to_hub._sync_state("switch.existing", state)

    web_client.async_create_virtual_device.assert_not_called()
    maker_client.send_command.assert_called_once_with("42", "off")
