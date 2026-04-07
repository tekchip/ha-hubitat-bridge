from unittest.mock import AsyncMock, MagicMock, mock_open, patch
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
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
            new_callable=AsyncMock,
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
    with (
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
            new_callable=AsyncMock,
            side_effect=Exception("unreachable"),
        ),
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
            new_callable=AsyncMock,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["hub_url"] == "cannot_connect"


async def test_invalid_token_shows_error(hass: HomeAssistant):
    import aiohttp
    with (
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
            new_callable=AsyncMock,
            side_effect=aiohttp.ClientResponseError(None, None, status=401),
        ),
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
            new_callable=AsyncMock,
        ),
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
        patch(
            "custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
            new_callable=AsyncMock,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["password"] == "invalid_auth"


async def test_reconfigure_updates_entry(hass: HomeAssistant):
    """Reconfigure flow validates and updates existing entry data."""
    with (
        patch("custom_components.ha_hubitat_bridge.async_setup_entry", return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
              new_callable=AsyncMock, return_value=[{"id": "1"}]),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
              new_callable=AsyncMock, return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
              new_callable=AsyncMock),
    ):
        # Create initial entry
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        entry = result["result"]

        # Start reconfigure flow
        result2 = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["step_id"] == "reconfigure"

        # Submit updated credentials
        new_input = {**VALID_INPUT, "token": "new-token"}
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"], user_input=new_input
        )

    assert result3["type"] == FlowResultType.ABORT
    assert result3["reason"] == "reconfigure_successful"
    assert entry.data["token"] == "new-token"


async def test_options_flow_no_icon(hass: HomeAssistant):
    """Options flow with blank icon URL saves without error."""
    with (
        patch("custom_components.ha_hubitat_bridge.async_setup_entry", return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
              new_callable=AsyncMock, return_value=[{"id": "1"}]),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
              new_callable=AsyncMock, return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
              new_callable=AsyncMock),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
        entry = result["result"]

    result2 = await hass.config_entries.options.async_init(entry.entry_id)
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "init"

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], user_input={"icon_url": ""}
    )
    assert result3["type"] == FlowResultType.CREATE_ENTRY


async def test_options_flow_icon_download_success(hass: HomeAssistant):
    """Options flow downloads and saves a valid icon URL."""
    with (
        patch("custom_components.ha_hubitat_bridge.async_setup_entry", return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
              new_callable=AsyncMock, return_value=[{"id": "1"}]),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
              new_callable=AsyncMock, return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
              new_callable=AsyncMock),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
        entry = result["result"]

    result2 = await hass.config_entries.options.async_init(entry.entry_id)

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.headers = {"Content-Type": "image/png"}
    mock_response.read = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("custom_components.ha_hubitat_bridge.config_flow.async_get_clientsession") as mock_sess,
        patch("pathlib.Path.write_bytes"),
    ):
        mock_sess.return_value.get.return_value = mock_response
        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"], user_input={"icon_url": "http://example.com/icon.png"}
        )

    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert result3["data"]["icon_url"] == "http://example.com/icon.png"


async def test_options_flow_icon_download_failure(hass: HomeAssistant):
    """Options flow shows error when icon URL returns non-image."""
    with (
        patch("custom_components.ha_hubitat_bridge.async_setup_entry", return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatMakerClient.get_devices",
              new_callable=AsyncMock, return_value=[{"id": "1"}]),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_login",
              new_callable=AsyncMock, return_value=True),
        patch("custom_components.ha_hubitat_bridge.config_flow.HubitatWebClient.async_close",
              new_callable=AsyncMock),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}, data=VALID_INPUT
        )
        entry = result["result"]

    result2 = await hass.config_entries.options.async_init(entry.entry_id)

    mock_response = MagicMock()
    mock_response.status = 404
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    with patch("custom_components.ha_hubitat_bridge.config_flow.async_get_clientsession") as mock_sess:
        mock_sess.return_value.get.return_value = mock_response
        result3 = await hass.config_entries.options.async_configure(
            result2["flow_id"], user_input={"icon_url": "http://example.com/bad.png"}
        )

    assert result3["type"] == FlowResultType.FORM
    assert result3["errors"]["icon_url"] == "icon_download_failed"
