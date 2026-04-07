import pytest
import aiohttp
from aioresponses import aioresponses

from custom_components.ha_hubitat_bridge.hubitat_client import HubitatMakerClient, HubitatWebClient

BASE = "http://10.10.10.7/apps/api/150"
TOKEN = "test-token"

DRIVER_LIST = [
    {"id": 92, "name": "Virtual Switch"},
    {"id": 101, "name": "Virtual Dimmer"},
    {"id": 105, "name": "Virtual Motion Sensor"},
    {"id": 113, "name": "Virtual Contact Sensor"},
]


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
    client = HubitatWebClient("http://10.10.10.7", "brock", "password123")
    yield client
    await client.async_close()


async def test_login_success(web_client):
    with aioresponses() as m:
        m.post("http://10.10.10.7/login", status=302, headers={"Location": "http://10.10.10.7/"})
        result = await web_client.async_login()
    assert result is True


async def test_login_failure_stays_on_login(web_client):
    with aioresponses() as m:
        m.post("http://10.10.10.7/login", status=200, headers={})
        result = await web_client.async_login()
    assert result is False


async def test_login_failure_redirects_to_login(web_client):
    """302 back to /login means wrong password."""
    with aioresponses() as m:
        m.post(
            "http://10.10.10.7/login",
            status=302,
            headers={"Location": "http://10.10.10.7/login"},
        )
        result = await web_client.async_login()
    assert result is False


async def test_create_virtual_device_returns_id(web_client):
    web_client._authenticated = True
    web_client._driver_map = {"Virtual Switch": 92}
    with aioresponses() as m:
        m.get(
            "http://10.10.10.7/device/createVirtual?deviceTypeId=92",
            payload={"success": True, "deviceId": 42},
        )
        m.get(
            "http://10.10.10.7/device/updateLabel?deviceId=42&label=Test+Switch",
            payload=True,
        )
        device_id = await web_client.async_create_virtual_device("Test Switch", "Virtual Switch")
    assert device_id == "42"


async def test_create_virtual_device_returns_none_on_failure(web_client):
    web_client._authenticated = True
    web_client._driver_map = {"Virtual Switch": 92}
    with aioresponses() as m:
        m.get(
            "http://10.10.10.7/device/createVirtual?deviceTypeId=92",
            payload={"success": False},
        )
        device_id = await web_client.async_create_virtual_device("Bad", "Virtual Switch")
    assert device_id is None


async def test_create_virtual_device_unknown_driver(web_client):
    web_client._authenticated = True
    web_client._driver_map = {"Virtual Switch": 92}
    device_id = await web_client.async_create_virtual_device("Test", "Nonexistent Driver")
    assert device_id is None


async def test_create_virtual_device_session_expired(web_client):
    """Redirect to /login during createVirtual means session expired."""
    web_client._authenticated = True
    web_client._driver_map = {"Virtual Switch": 92}
    with aioresponses() as m:
        m.get(
            "http://10.10.10.7/device/createVirtual?deviceTypeId=92",
            status=302,
            headers={"Location": "http://10.10.10.7/login"},
        )
        device_id = await web_client.async_create_virtual_device("Test", "Virtual Switch")
    assert device_id is None
    assert web_client._authenticated is False


async def test_load_driver_map(web_client):
    """_load_driver_map populates _driver_map from /driver/list/data."""
    with aioresponses() as m:
        m.get("http://10.10.10.7/driver/list/data", payload=DRIVER_LIST)
        await web_client._load_driver_map()
    assert web_client._driver_map == {
        "Virtual Switch": 92,
        "Virtual Dimmer": 101,
        "Virtual Motion Sensor": 105,
        "Virtual Contact Sensor": 113,
    }
