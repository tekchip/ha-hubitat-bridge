import pytest
import aiohttp
from aioresponses import aioresponses

from custom_components.ha_hubitat_bridge.hubitat_client import HubitatMakerClient, HubitatWebClient

BASE = "http://10.10.10.7/apps/api/150"
TOKEN = "test-token"


@pytest.fixture
async def maker_client():
    session = aiohttp.ClientSession()
    yield HubitatMakerClient("http://10.10.10.7", 150, TOKEN, session)
    await session.close()


async def test_get_devices_returns_list(maker_client):
    with aioresponses() as m:
        m.get(f"{BASE}/devices?access_token={TOKEN}", payload=[{"id": "1", "name": "Switch"}])
        result = await maker_client.get_devices()
    assert result == [{"id": "1", "name": "Switch"}]


async def test_get_device_detail(maker_client):
    with aioresponses() as m:
        m.get(
            f"{BASE}/devices/1?access_token={TOKEN}",
            payload={"id": "1", "capabilities": ["Switch"], "attributes": []},
        )
        result = await maker_client.get_device("1")
    assert result["capabilities"] == ["Switch"]


async def test_send_command_no_value(maker_client):
    with aioresponses() as m:
        m.get(f"{BASE}/devices/1/on?access_token={TOKEN}", payload={"result": "ok"})
        result = await maker_client.send_command("1", "on")
    assert result == {"result": "ok"}


async def test_send_command_with_value(maker_client):
    with aioresponses() as m:
        m.get(f"{BASE}/devices/1/setLevel/80?access_token={TOKEN}", payload={"result": "ok"})
        result = await maker_client.send_command("1", "setLevel", "80")
    assert result == {"result": "ok"}


async def test_http_error_raises(maker_client):
    with aioresponses() as m:
        m.get(f"{BASE}/devices?access_token={TOKEN}", status=401)
        with pytest.raises(aiohttp.ClientResponseError):
            await maker_client.get_devices()


async def test_subscribe_url_encodes_callback(maker_client):
    with aioresponses() as m:
        m.get(
            f"{BASE}/subscribeURL/http%3A%2F%2F10.10.10.10%3A8123%2Fapi%2Fwebhook%2Fabc?access_token={TOKEN}",
            payload={"result": "ok"},
        )
        result = await maker_client.subscribe_url("http://10.10.10.10:8123/api/webhook/abc")
    assert result == {"result": "ok"}


@pytest.fixture
async def web_client():
    session = aiohttp.ClientSession()
    yield HubitatWebClient("http://10.10.10.7", "brock", "password123", session)
    await session.close()


async def test_login_success(web_client):
    with aioresponses() as m:
        # Hubitat redirects to "/" on successful login
        m.post("http://10.10.10.7/login", status=302, headers={"Location": "http://10.10.10.7/"})
        result = await web_client.async_login()
    assert result is True


async def test_login_failure_stays_on_login(web_client):
    with aioresponses() as m:
        # Stays on /login page on failure
        m.post("http://10.10.10.7/login", status=200, headers={})
        result = await web_client.async_login()
    assert result is False


async def test_create_virtual_device_returns_id(web_client):
    web_client._authenticated = True
    with aioresponses() as m:
        # Hubitat redirects to /device/edit/{id} after creating
        m.post(
            "http://10.10.10.7/device/update",
            status=302,
            headers={"Location": "http://10.10.10.7/device/edit/42"},
        )
        device_id = await web_client.async_create_virtual_device("Test Switch", "Virtual Switch")
    assert device_id == "42"


async def test_create_virtual_device_returns_none_on_error(web_client):
    web_client._authenticated = True
    with aioresponses() as m:
        m.post("http://10.10.10.7/device/update", status=500)
        device_id = await web_client.async_create_virtual_device("Bad", "Virtual Switch")
    assert device_id is None
