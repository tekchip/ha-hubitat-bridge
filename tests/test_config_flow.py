from unittest.mock import AsyncMock, patch
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_hubitat_bridge.const import DOMAIN

VALID_INPUT = {
    "hub_url": "http://10.10.10.7",
    "app_id": 150,
    "token": "test-token",
    "username": "brock",
    "password": "secret",
}


async def test_form_shows(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_valid_input_creates_entry(hass: HomeAssistant):
    with (
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
            new_callable=AsyncMock,
            return_value=[{"id": "1"}],
        ),
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
            new_callable=AsyncMock,
            return_value=True,
        ),
        patch(
            "custom_components.ha_hubitat_bridge.async_setup_entry",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hubitat Bridge"
    assert result["data"] == VALID_INPUT


async def test_cannot_connect_shows_error(hass: HomeAssistant):
    with patch(
        "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
        new_callable=AsyncMock,
        side_effect=Exception("unreachable"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["hub_url"] == "cannot_connect"


async def test_invalid_token_shows_error(hass: HomeAssistant):
    import aiohttp
    with patch(
        "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
        new_callable=AsyncMock,
        side_effect=aiohttp.ClientResponseError(None, None, status=401),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["token"] == "invalid_token"


async def test_invalid_auth_shows_error(hass: HomeAssistant):
    with (
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["password"] == "invalid_auth"
