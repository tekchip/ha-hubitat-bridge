# HA Hubitat Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable HA custom integration that provides full bidirectional device mirroring between Home Assistant and Hubitat Elevation with a config flow UI and automatic device discovery.

**Architecture:** A single `ha_hubitat_bridge` custom component. `HubitatCoordinator` fetches Hubitat Maker API devices, creates HA entities, and processes real-time webhook events (with 60s polling fallback for new devices). `HAToHubitat` listens to HA `state_changed`, filters qualifying entities, auto-creates Hubitat virtual devices via the Hubitat web UI API, and dispatches state commands via Maker API. Retry (3× exponential backoff) and `persistent_notification` on all outbound failures.

**Tech Stack:** Python 3.12+, HA custom integration framework (`config_entries`, `entity_platform`, `webhook`, `storage`, `dispatcher`), `aiohttp` (HA-bundled), `pytest` + `pytest-asyncio` + `pytest-homeassistant-custom-component` + `aioresponses`

---

## File Map

```
custom_components/ha_hubitat_bridge/
  __init__.py           ← entry setup/teardown; wires coordinator + HAToHubitat
  manifest.json         ← HA + HACS metadata
  const.py              ← DOMAIN, PLATFORMS, config keys, capability/driver maps
  hubitat_client.py     ← HubitatMakerClient (Maker API) + HubitatWebClient (web auth + device create)
  entity_map.py         ← EntityMap: persistent entity_id ↔ Hubitat device_id via HA Store
  hubitat_to_ha.py      ← HubitatCoordinator + HubitatEntity base class
  ha_to_hubitat.py      ← HAToHubitat: state_changed listener, device creation, command dispatch
  switch.py             ← HubitatSwitch
  light.py              ← HubitatLight
  binary_sensor.py      ← HubitatMotionSensor, HubitatContactSensor, HubitatWaterSensor, HubitatSmokeSensor
  sensor.py             ← HubitatTemperatureSensor, HubitatHumiditySensor, HubitatIlluminanceSensor, HubitatPowerSensor
  lock.py               ← HubitatLock
  cover.py              ← HubitatCover
  climate.py            ← HubitatClimate
  fan.py                ← HubitatFan
  strings.json          ← config flow UI strings
  translations/en.json  ← English translations
hacs.json
tests/
  conftest.py
  test_hubitat_client.py
  test_entity_map.py
  test_config_flow.py
  test_hubitat_to_ha.py
  test_ha_to_hubitat.py
  test_switch.py
  test_light.py
  test_binary_sensor.py
  test_sensor.py
  test_lock.py
  test_cover.py
  test_climate.py
  test_fan.py
pyproject.toml
```

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `custom_components/ha_hubitat_bridge/manifest.json`
- Create: `custom_components/ha_hubitat_bridge/const.py`
- Create: `custom_components/ha_hubitat_bridge/strings.json`
- Create: `custom_components/ha_hubitat_bridge/translations/en.json`
- Create: `hacs.json`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["custom_components*"]
```

- [ ] **Step 2: Install dev dependencies**

```bash
pip install pytest pytest-asyncio pytest-homeassistant-custom-component aioresponses
```

Expected: all packages install without error.

- [ ] **Step 3: Create manifest.json**

```json
{
  "domain": "ha_hubitat_bridge",
  "name": "Hubitat Bridge",
  "version": "0.1.0",
  "config_flow": true,
  "documentation": "https://github.com/YOUR_USERNAME/ha-hubitat-bridge",
  "issue_tracker": "https://github.com/YOUR_USERNAME/ha-hubitat-bridge/issues",
  "iot_class": "local_push",
  "requirements": [],
  "codeowners": []
}
```

- [ ] **Step 4: Create hacs.json**

```json
{
  "name": "Hubitat Bridge",
  "description": "Bidirectional device mirroring between Home Assistant and Hubitat Elevation",
  "content_in_root": false,
  "homeassistant": "2024.1.0"
}
```

- [ ] **Step 5: Create const.py**

```python
from __future__ import annotations

DOMAIN = "ha_hubitat_bridge"

PLATFORMS = ["switch", "light", "binary_sensor", "sensor", "lock", "cover", "climate", "fan"]

CONF_HUB_URL = "hub_url"
CONF_APP_ID = "app_id"
CONF_TOKEN = "token"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

POLL_INTERVAL = 60  # seconds

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device_{{entry_id}}"

IGNORE_LABEL = "hubitat-ignore"

MIRROR_DOMAINS = frozenset({
    "switch", "light", "binary_sensor", "sensor", "lock",
    "cover", "climate", "fan", "media_player", "vacuum", "input_boolean",
})

# Capability → platform. SwitchLevel must come before Switch so dimmers → light.
CAPABILITY_TO_PLATFORM: dict[str, str] = {
    "SwitchLevel": "light",
    "Switch": "switch",
    "MotionSensor": "binary_sensor",
    "ContactSensor": "binary_sensor",
    "WaterSensor": "binary_sensor",
    "SmokeDetector": "binary_sensor",
    "TemperatureMeasurement": "sensor",
    "RelativeHumidityMeasurement": "sensor",
    "IlluminanceMeasurement": "sensor",
    "PowerMeter": "sensor",
    "Lock": "lock",
    "GarageDoorControl": "cover",
    "Thermostat": "climate",
    "FanControl": "fan",
}

BINARY_SENSOR_CLASS_TO_DRIVER: dict[str | None, str] = {
    "motion": "Virtual Motion Sensor",
    "door": "Virtual Contact Sensor",
    "window": "Virtual Contact Sensor",
    "contact": "Virtual Contact Sensor",
    "garage_door": "Virtual Contact Sensor",
    "moisture": "Virtual Water Sensor",
    "smoke": "Virtual Smoke Detector",
    None: "Virtual Contact Sensor",
}

SENSOR_CLASS_TO_DRIVER: dict[str | None, str] = {
    "temperature": "Virtual Temperature Sensor",
    "humidity": "Virtual Humidity Sensor",
    "illuminance": "Virtual Illuminance Sensor",
    None: "Virtual Omni Sensor",
}

HA_DOMAIN_TO_DRIVER: dict[str, str] = {
    "switch": "Virtual Switch",
    "input_boolean": "Virtual Switch",
    "lock": "Virtual Lock",
    "cover": "Virtual Garage Door Control",
    "climate": "Virtual Thermostat",
    "fan": "Virtual Fan Controller",
    "media_player": "Virtual Switch",
    "vacuum": "Virtual Switch",
}
```

- [ ] **Step 6: Create strings.json and translations/en.json (identical content)**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect to Hubitat",
        "description": "Enter your Hubitat Elevation hub details. The Maker API app must be set to expose **All Devices**.",
        "data": {
          "hub_url": "Hub URL",
          "app_id": "Maker API App ID",
          "token": "Maker API Access Token",
          "username": "Hub Username",
          "password": "Hub Password"
        }
      }
    },
    "error": {
      "cannot_connect": "Unable to reach the hub. Check the Hub URL.",
      "invalid_auth": "Invalid credentials. Check token, username, and password.",
      "unknown": "Unexpected error. See logs for details."
    },
    "abort": {
      "already_configured": "Hubitat Bridge is already configured."
    }
  }
}
```

- [ ] **Step 7: Create tests/conftest.py**

```python
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield
```

- [ ] **Step 8: Run pytest to confirm scaffold**

```bash
pytest tests/ -v --co
```

Expected: "no tests ran" with 0 errors (collection passes, no test files yet have tests).

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml hacs.json custom_components/ tests/conftest.py
git commit -m "feat: project scaffold — manifest, const, strings, test infra"
```

---

### Task 2: HubitatMakerClient

**Files:**
- Create: `custom_components/ha_hubitat_bridge/hubitat_client.py` (MakerClient section)
- Create: `tests/test_hubitat_client.py` (MakerClient tests)

- [ ] **Step 1: Write failing tests for HubitatMakerClient**

```python
# tests/test_hubitat_client.py
import pytest
import aiohttp
from aioresponses import aioresponses

from custom_components.ha_hubitat_bridge.hubitat_client import HubitatMakerClient

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
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_hubitat_client.py -v
```

Expected: ImportError — `hubitat_client` does not exist yet.

- [ ] **Step 3: Implement HubitatMakerClient in hubitat_client.py**

```python
# custom_components/ha_hubitat_bridge/hubitat_client.py
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
import uuid
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_RETRY_DELAYS = (0, 2, 8)  # seconds before attempt 1, 2, 3


async def _with_retry(coro_factory, label: str) -> Any:
    """Run coro_factory() up to 3 times with exponential backoff. Re-raises on final failure."""
    last_exc: Exception | None = None
    for delay in _RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _LOGGER.warning("Hubitat API call '%s' failed (retrying): %s", label, exc)
    raise last_exc


class HubitatMakerClient:
    """Client for Hubitat Maker API REST calls."""

    def __init__(
        self,
        hub_url: str,
        app_id: int,
        token: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._base = f"{hub_url.rstrip('/')}/apps/api/{app_id}"
        self._token = token
        self._session = session

    async def get_devices(self) -> list[dict]:
        return await _with_retry(lambda: self._get("/devices"), "get_devices")

    async def get_device(self, device_id: str) -> dict:
        return await _with_retry(lambda: self._get(f"/devices/{device_id}"), f"get_device/{device_id}")

    async def send_command(self, device_id: str, command: str, value: str | None = None) -> Any:
        path = f"/devices/{device_id}/{command}"
        if value is not None:
            path += f"/{value}"
        return await _with_retry(lambda: self._get(path), f"send_command/{device_id}/{command}")

    async def subscribe_url(self, callback_url: str) -> Any:
        encoded = urllib.parse.quote(callback_url, safe="")
        return await _with_retry(lambda: self._get(f"/subscribeURL/{encoded}"), "subscribe_url")

    async def _get(self, path: str) -> Any:
        url = f"{self._base}{path}?access_token={self._token}"
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_hubitat_client.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/hubitat_client.py tests/test_hubitat_client.py
git commit -m "feat: HubitatMakerClient with retry"
```

---

### Task 3: HubitatWebClient (virtual device creation)

**Files:**
- Modify: `custom_components/ha_hubitat_bridge/hubitat_client.py` (add HubitatWebClient)
- Modify: `tests/test_hubitat_client.py` (add WebClient tests)

> **Note on Hubitat's internal API:** Before implementing this task, verify the exact device-creation endpoint by opening `http://10.10.10.7` in a browser, logging in, navigating to **Devices → Add Virtual Device**, filling out the form, and submitting while watching the Network tab in DevTools. Capture: the POST URL, form field names, and redirect URL pattern. The implementation below uses the most common pattern found in community Hubitat tools — adjust field names if the observed traffic differs.

- [ ] **Step 1: Write failing tests for HubitatWebClient**

Append to `tests/test_hubitat_client.py`:

```python
from custom_components.ha_hubitat_bridge.hubitat_client import HubitatWebClient


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
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_hubitat_client.py -v -k "web"
```

Expected: ImportError or AttributeError — `HubitatWebClient` not defined yet.

- [ ] **Step 3: Implement HubitatWebClient**

Append to `custom_components/ha_hubitat_bridge/hubitat_client.py`:

```python
class HubitatWebClient:
    """
    Authenticated client for Hubitat's web UI.
    Used exclusively for creating virtual devices, which the Maker API cannot do.
    """

    def __init__(
        self,
        hub_url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._hub_url = hub_url.rstrip("/")
        self._username = username
        self._password = password
        self._session = session
        self._authenticated = False

    async def async_login(self) -> bool:
        """POST credentials to /login. Returns True if Hubitat redirects away from /login."""
        url = f"{self._hub_url}/login"
        data = {"loginName": self._username, "loginPassword": self._password}
        try:
            async with self._session.post(
                url, data=data, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                final = str(resp.url).rstrip("/")
                self._authenticated = not final.endswith("/login")
                return self._authenticated
        except Exception as exc:
            _LOGGER.error("Hubitat web login failed: %s", exc)
            self._authenticated = False
            return False

    async def async_create_virtual_device(self, name: str, driver: str) -> str | None:
        """
        Create a virtual device on Hubitat.
        Returns the new Hubitat device ID string, or None on failure.
        POST /device/update → Hubitat redirects to /device/edit/{id}.
        """
        if not self._authenticated:
            if not await self.async_login():
                return None

        url = f"{self._hub_url}/device/update"
        network_id = f"hab-{uuid.uuid4().hex[:8]}"
        data = {
            "action": "new",
            "deviceType": driver,
            "deviceName": name,
            "deviceLabel": name,
            "hub": "1",
            "deviceNetworkId": network_id,
        }
        try:
            async with self._session.post(
                url, data=data, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                if "/device/edit/" in final_url:
                    return final_url.split("/device/edit/")[-1].split("?")[0].strip()
                # Fallback: scan response body for redirect hint
                body = await resp.text()
                match = re.search(r"/device/edit/(\d+)", body)
                return match.group(1) if match else None
        except Exception as exc:
            _LOGGER.error("Failed to create virtual device '%s' (%s): %s", name, driver, exc)
            return None
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_hubitat_client.py -v
```

Expected: all 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/hubitat_client.py tests/test_hubitat_client.py
git commit -m "feat: HubitatWebClient for virtual device creation"
```

---

### Task 4: EntityMap

**Files:**
- Create: `custom_components/ha_hubitat_bridge/entity_map.py`
- Create: `tests/test_entity_map.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_entity_map.py
import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_hubitat_bridge.entity_map import EntityMap


async def test_put_and_get(hass: HomeAssistant):
    em = EntityMap(hass)
    await em.async_load()
    em.put("switch.my_switch", "42")
    assert em.get("switch.my_switch") == "42"


async def test_get_missing_returns_none(hass: HomeAssistant):
    em = EntityMap(hass)
    await em.async_load()
    assert em.get("switch.nonexistent") is None


async def test_has(hass: HomeAssistant):
    em = EntityMap(hass)
    await em.async_load()
    em.put("light.desk", "7")
    assert em.has("light.desk") is True
    assert em.has("light.unknown") is False


async def test_all_entity_ids(hass: HomeAssistant):
    em = EntityMap(hass)
    await em.async_load()
    em.put("switch.a", "1")
    em.put("light.b", "2")
    assert set(em.all_entity_ids()) == {"switch.a", "light.b"}


async def test_persistence_across_instances(hass: HomeAssistant):
    em1 = EntityMap(hass)
    await em1.async_load()
    em1.put("sensor.temp", "99")
    await em1.async_save()

    em2 = EntityMap(hass)
    await em2.async_load()
    assert em2.get("sensor.temp") == "99"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_entity_map.py -v
```

Expected: ImportError — `entity_map` not defined.

- [ ] **Step 3: Implement EntityMap**

```python
# custom_components/ha_hubitat_bridge/entity_map.py
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_STORAGE_VERSION = 1
_STORAGE_KEY = f"{DOMAIN}.entity_map"


class EntityMap:
    """Persistent mapping between HA entity_id and Hubitat device ID."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store = Store(hass, _STORAGE_VERSION, _STORAGE_KEY)
        self._data: dict[str, str] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        self._data = stored or {}

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    def put(self, entity_id: str, hubitat_device_id: str) -> None:
        self._data[entity_id] = hubitat_device_id

    def get(self, entity_id: str) -> str | None:
        return self._data.get(entity_id)

    def has(self, entity_id: str) -> bool:
        return entity_id in self._data

    def all_entity_ids(self) -> list[str]:
        return list(self._data.keys())
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_entity_map.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/entity_map.py tests/test_entity_map.py
git commit -m "feat: EntityMap persistent storage"
```

---

### Task 5: Config flow

**Files:**
- Create: `custom_components/ha_hubitat_bridge/config_flow.py`
- Create: `custom_components/ha_hubitat_bridge/__init__.py` (stub only — wired fully in Task 7)
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config_flow.py
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
            "custom_components.ha_hubitat_bridge.__init__.async_setup_entry",
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
    assert result["errors"]["base"] == "cannot_connect"


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
    assert result["errors"]["base"] == "invalid_auth"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_config_flow.py -v
```

Expected: ImportError or no config flow found.

- [ ] **Step 3: Create __init__.py stub**

```python
# custom_components/ha_hubitat_bridge/__init__.py
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Hubitat Bridge (stub — wired fully in Task 7)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
```

- [ ] **Step 4: Create config_flow.py**

```python
# custom_components/ha_hubitat_bridge/config_flow.py
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_APP_ID,
    CONF_HUB_URL,
    CONF_PASSWORD,
    CONF_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)
from .hubitat_client import HubitatMakerClient, HubitatWebClient

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HUB_URL, default="http://"): str,
        vol.Required(CONF_APP_ID): vol.Coerce(int),
        vol.Required(CONF_TOKEN): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class HubitatBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            maker = HubitatMakerClient(
                user_input[CONF_HUB_URL],
                user_input[CONF_APP_ID],
                user_input[CONF_TOKEN],
                session,
            )
            web = HubitatWebClient(
                user_input[CONF_HUB_URL],
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                session,
            )

            try:
                await maker.get_devices()
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                ok = await web.async_login()
                if not ok:
                    errors["base"] = "invalid_auth"

            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Hubitat Bridge", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_SCHEMA,
            errors=errors,
        )
```

- [ ] **Step 5: Run tests and confirm they pass**

```bash
pytest tests/test_config_flow.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ha_hubitat_bridge/__init__.py custom_components/ha_hubitat_bridge/config_flow.py tests/test_config_flow.py
git commit -m "feat: config flow UI with Maker API + web credential validation"
```

---

### Task 6: HubitatCoordinator and HubitatEntity base

**Files:**
- Create: `custom_components/ha_hubitat_bridge/hubitat_to_ha.py`
- Create: `tests/test_hubitat_to_ha.py`

- [ ] **Step 1: Write failing tests**

```python
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
    assert any(d["id"] == "3" for d in signals)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_hubitat_to_ha.py -v
```

Expected: ImportError — `hubitat_to_ha` not defined.

- [ ] **Step 3: Implement hubitat_to_ha.py**

```python
# custom_components/ha_hubitat_bridge/hubitat_to_ha.py
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.webhook import async_register as webhook_register, async_unregister as webhook_unregister

from .const import DOMAIN, POLL_INTERVAL, SIGNAL_NEW_DEVICE

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from .hubitat_client import HubitatMakerClient

_LOGGER = logging.getLogger(__name__)


class HubitatCoordinator:
    """
    Manages Hubitat→HA sync:
    - Fetches device list + details from Maker API
    - Registers HA webhook and subscribes Hubitat to send events there
    - Polls every 60s for new devices and signals platforms via dispatcher
    - Routes incoming webhook events to registered entities
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        maker_client: HubitatMakerClient,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self.maker_client = maker_client
        self.hubitat_devices: dict[str, dict] = {}  # device_id → full device dict
        self._entities: dict[str, list[HubitatEntity]] = {}  # device_id → entities
        self._webhook_id = f"ha_hubitat_bridge_{entry.entry_id}"

    async def async_setup(self) -> None:
        webhook_register(self.hass, DOMAIN, "Hubitat Bridge Events", self._webhook_id, self._handle_webhook)

        # Subscribe Hubitat to POST events to our webhook
        try:
            api = self.hass.config.api
            if api:
                callback_url = f"http://{api.local_ip}:{api.port}/api/webhook/{self._webhook_id}"
                await self.maker_client.subscribe_url(callback_url)
        except Exception as exc:
            _LOGGER.warning("Could not subscribe Hubitat event URL: %s", exc)

        await self._async_fetch_all_devices()

        unsub = async_track_time_interval(
            self.hass, self._async_poll, timedelta(seconds=POLL_INTERVAL)
        )
        self._entry.async_on_unload(unsub)
        self._entry.async_on_unload(lambda: webhook_unregister(self.hass, self._webhook_id))

    async def _async_fetch_all_devices(self) -> None:
        try:
            device_stubs = await self.maker_client.get_devices()
        except Exception as exc:
            _LOGGER.error("Failed to fetch Hubitat device list: %s", exc)
            return

        for stub in device_stubs:
            device_id = str(stub["id"])
            if device_id not in self.hubitat_devices:
                try:
                    detail = await self.maker_client.get_device(device_id)
                    self.hubitat_devices[device_id] = detail
                except Exception as exc:
                    _LOGGER.warning("Could not fetch device %s detail: %s", device_id, exc)

    async def _async_poll(self, _now) -> None:
        try:
            stubs = await self.maker_client.get_devices()
        except Exception as exc:
            _LOGGER.warning("Device poll failed: %s", exc)
            return

        for stub in stubs:
            device_id = str(stub["id"])
            if device_id not in self.hubitat_devices:
                try:
                    detail = await self.maker_client.get_device(device_id)
                    self.hubitat_devices[device_id] = detail
                    async_dispatcher_send(
                        self.hass,
                        SIGNAL_NEW_DEVICE.format(entry_id=self._entry.entry_id),
                        detail,
                    )
                except Exception as exc:
                    _LOGGER.warning("Could not fetch new device %s: %s", device_id, exc)

    async def _handle_webhook(self, hass: HomeAssistant, webhook_id: str, request) -> None:
        try:
            data = await request.json()
        except Exception:
            return
        content = data.get("content", data)
        device_id = str(content.get("deviceId", ""))
        attribute = str(content.get("name", ""))
        value = str(content.get("value", ""))

        for entity in self._entities.get(device_id, []):
            try:
                entity.handle_event(attribute, value)
            except Exception as exc:
                _LOGGER.warning("Error dispatching event to entity %s: %s", entity.entity_id, exc)

    def register_entity(self, device_id: str, entity: HubitatEntity) -> None:
        self._entities.setdefault(device_id, []).append(entity)

    def unregister_entity(self, device_id: str, entity: HubitatEntity) -> None:
        if device_id in self._entities:
            try:
                self._entities[device_id].remove(entity)
            except ValueError:
                pass


class HubitatEntity(Entity):
    """Base class for all Hubitat-sourced HA entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        self._device = device
        self._coordinator = coordinator
        self._device_id = str(device["id"])
        self._attr_unique_id = f"hubitat_{self._device_id}"
        self._attr_name = device.get("label") or device.get("name")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device.get("label") or self._device.get("name"),
            manufacturer="Hubitat",
            model=self._device.get("type"),
        )

    def _get_attr(self, name: str) -> str | None:
        for a in self._device.get("attributes", []):
            if a["name"] == name:
                v = a.get("currentValue")
                return str(v) if v is not None else None
        return None

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_entity(self._device_id, self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_entity(self._device_id, self)

    def handle_event(self, attribute: str, value: str) -> None:
        """Override in subclasses to process Hubitat attribute events."""
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
pytest tests/test_hubitat_to_ha.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/hubitat_to_ha.py tests/test_hubitat_to_ha.py
git commit -m "feat: HubitatCoordinator and HubitatEntity base"
```

---

### Task 7: Integration wiring (__init__.py)

**Files:**
- Modify: `custom_components/ha_hubitat_bridge/__init__.py` (replace stub with full setup)

- [ ] **Step 1: Write failing tests for integration setup**

Append to `tests/test_hubitat_to_ha.py`:

```python
from unittest.mock import AsyncMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component


async def test_integration_loads(hass: HomeAssistant, mock_maker_client, mock_entry):
    """Integration async_setup_entry wires coordinator and does not raise."""
    from custom_components.ha_hubitat_bridge import async_setup_entry

    with (
        patch("custom_components.ha_hubitat_bridge.HubitatMakerClient", return_value=mock_maker_client),
        patch("custom_components.ha_hubitat_bridge.HubitatWebClient"),
        patch("custom_components.ha_hubitat_bridge.HubitatCoordinator.async_setup", new_callable=AsyncMock),
        patch("custom_components.ha_hubitat_bridge.HAToHubitat.async_setup", new_callable=AsyncMock),
        patch("custom_components.ha_hubitat_bridge.EntityMap.async_load", new_callable=AsyncMock),
        patch("homeassistant.config_entries.ConfigEntries.async_forward_entry_setups", new_callable=AsyncMock),
    ):
        mock_entry.data = {
            "hub_url": "http://10.10.10.7",
            "app_id": 150,
            "token": "tok",
            "username": "u",
            "password": "p",
        }
        result = await async_setup_entry(hass, mock_entry)
    assert result is True
```

- [ ] **Step 2: Run to confirm test fails**

```bash
pytest tests/test_hubitat_to_ha.py::test_integration_loads -v
```

Expected: FAIL (stub __init__.py doesn't wire coordinator).

- [ ] **Step 3: Replace __init__.py with full wiring**

```python
# custom_components/ha_hubitat_bridge/__init__.py
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_APP_ID, CONF_HUB_URL, CONF_PASSWORD, CONF_TOKEN, CONF_USERNAME, DOMAIN, PLATFORMS
from .entity_map import EntityMap
from .ha_to_hubitat import HAToHubitat
from .hubitat_client import HubitatMakerClient, HubitatWebClient
from .hubitat_to_ha import HubitatCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)

    maker_client = HubitatMakerClient(
        entry.data[CONF_HUB_URL],
        entry.data[CONF_APP_ID],
        entry.data[CONF_TOKEN],
        session,
    )
    web_client = HubitatWebClient(
        entry.data[CONF_HUB_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        session,
    )
    entity_map = EntityMap(hass)
    await entity_map.async_load()

    coordinator = HubitatCoordinator(hass, entry, maker_client)
    ha_to_hubitat = HAToHubitat(hass, entry, maker_client, web_client, entity_map)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "ha_to_hubitat": ha_to_hubitat,
    }

    await coordinator.async_setup()
    await ha_to_hubitat.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id, {})
        ha_to_hubitat: HAToHubitat | None = data.get("ha_to_hubitat")
        if ha_to_hubitat:
            await ha_to_hubitat.async_teardown()
    return unload_ok
```

- [ ] **Step 4: Create ha_to_hubitat.py stub** (full implementation in Task 16)

```python
# custom_components/ha_hubitat_bridge/ha_to_hubitat.py
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .entity_map import EntityMap
from .hubitat_client import HubitatMakerClient, HubitatWebClient


class HAToHubitat:
    """Stub — fully implemented in Task 16."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        maker_client: HubitatMakerClient,
        web_client: HubitatWebClient,
        entity_map: EntityMap,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._maker_client = maker_client
        self._web_client = web_client
        self._entity_map = entity_map
        self._unsub = None

    async def async_setup(self) -> None:
        pass

    async def async_teardown(self) -> None:
        if self._unsub:
            self._unsub()
```

- [ ] **Step 5: Run the integration load test**

```bash
pytest tests/test_hubitat_to_ha.py::test_integration_loads -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ha_hubitat_bridge/__init__.py custom_components/ha_hubitat_bridge/ha_to_hubitat.py
git commit -m "feat: integration wiring, entry setup/unload"
```

---

### Task 8: switch.py — HubitatSwitch

**Files:**
- Create: `custom_components/ha_hubitat_bridge/switch.py`
- Create: `tests/test_switch.py`

The platform pattern established here is reused in Tasks 9–15. Each platform:
1. Filters `coordinator.hubitat_devices` for its capabilities in `async_setup_entry`
2. Connects to `SIGNAL_NEW_DEVICE` to auto-add future devices
3. Entity subclasses `HubitatEntity` and implements `handle_event` + control methods

- [ ] **Step 1: Write failing tests**

```python
# tests/test_switch.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant

DEVICE = {
    "id": "1",
    "name": "Living Room Switch",
    "label": "Living Room Switch",
    "type": "Generic Zigbee Switch",
    "capabilities": ["Switch"],
    "attributes": [{"name": "switch", "currentValue": "on", "dataType": "ENUM"}],
}


@pytest.fixture
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    coord = MagicMock(spec=HubitatCoordinator)
    coord.hass = hass
    coord.hubitat_devices = {"1": DEVICE}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_switch_is_on(coordinator):
    from custom_components.ha_hubitat_bridge.switch import HubitatSwitch
    sw = HubitatSwitch(DEVICE, coordinator)
    assert sw.is_on is True


async def test_switch_is_off_when_attribute_off():
    from custom_components.ha_hubitat_bridge.switch import HubitatSwitch
    device = {**DEVICE, "attributes": [{"name": "switch", "currentValue": "off", "dataType": "ENUM"}]}
    coord = MagicMock()
    coord.maker_client = AsyncMock()
    sw = HubitatSwitch(device, coord)
    assert sw.is_on is False


async def test_handle_event_updates_state(hass, coordinator):
    from custom_components.ha_hubitat_bridge.switch import HubitatSwitch
    sw = HubitatSwitch(DEVICE, coordinator)
    sw.hass = hass
    sw.handle_event("switch", "off")
    assert sw.is_on is False


async def test_turn_on_sends_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.switch import HubitatSwitch
    sw = HubitatSwitch(DEVICE, coordinator)
    sw.hass = hass
    await sw.async_turn_on()
    coordinator.maker_client.send_command.assert_called_once_with("1", "on")


async def test_turn_off_sends_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.switch import HubitatSwitch
    sw = HubitatSwitch(DEVICE, coordinator)
    sw.hass = hass
    await sw.async_turn_off()
    coordinator.maker_client.send_command.assert_called_once_with("1", "off")


async def test_dimmer_excluded_from_switch(coordinator):
    """Devices with SwitchLevel should not be HubitatSwitch entities."""
    from custom_components.ha_hubitat_bridge.switch import _is_switch
    dimmer = {**DEVICE, "capabilities": ["Switch", "SwitchLevel"]}
    assert _is_switch(dimmer) is False
    assert _is_switch(DEVICE) is True
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_switch.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement switch.py**

```python
# custom_components/ha_hubitat_bridge/switch.py
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_switch(device: dict) -> bool:
    caps = device.get("capabilities", [])
    return "Switch" in caps and "SwitchLevel" not in caps


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatSwitch(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_switch(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_switch(device):
            async_add_entities([HubitatSwitch(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatSwitch(HubitatEntity, SwitchEntity):
    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            self._attr_is_on = value == "on"
            self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_is_on = False
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_switch.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/switch.py tests/test_switch.py
git commit -m "feat: HubitatSwitch entity platform"
```

---

### Task 9: light.py — HubitatLight

**Files:**
- Create: `custom_components/ha_hubitat_bridge/light.py`
- Create: `tests/test_light.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_light.py
from unittest.mock import AsyncMock, MagicMock
import pytest

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
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    coord = MagicMock(spec=HubitatCoordinator)
    coord.hass = hass
    coord.hubitat_devices = {"2": DIMMER}
    coord.maker_client = AsyncMock()
    coord.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_light_is_on(coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    assert lt.is_on is True


async def test_light_brightness_scaled(coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    # Hubitat 0-100 → HA 0-255
    assert lt.brightness == int(80 / 100 * 255)


async def test_handle_event_switch(hass, coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    lt.handle_event("switch", "off")
    assert lt.is_on is False


async def test_handle_event_level(hass, coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    lt.handle_event("level", "50")
    assert lt.brightness == int(50 / 100 * 255)


async def test_turn_on_with_brightness(hass, coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    await lt.async_turn_on(brightness=128)
    # 128/255*100 ≈ 50
    coordinator.maker_client.send_command.assert_any_call("2", "setLevel", "50")


async def test_turn_on_no_brightness(hass, coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    await lt.async_turn_on()
    coordinator.maker_client.send_command.assert_any_call("2", "on")


async def test_turn_off(hass, coordinator):
    from custom_components.ha_hubitat_bridge.light import HubitatLight
    lt = HubitatLight(DIMMER, coordinator)
    lt.hass = hass
    await lt.async_turn_off()
    coordinator.maker_client.send_command.assert_called_once_with("2", "off")
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_light.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement light.py**

```python
# custom_components/ha_hubitat_bridge/light.py
from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_light(device: dict) -> bool:
    return "SwitchLevel" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatLight(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_light(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_light(device):
            async_add_entities([HubitatLight(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatLight(HubitatEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"
        level = self._get_attr("level")
        self._attr_brightness = int(float(level) / 100 * 255) if level is not None else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            self._attr_is_on = value == "on"
        elif attribute == "level":
            self._attr_brightness = int(float(value) / 100 * 255)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            level = str(round(kwargs[ATTR_BRIGHTNESS] / 255 * 100))
            await self._coordinator.maker_client.send_command(self._device_id, "setLevel", level)
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        else:
            await self._coordinator.maker_client.send_command(self._device_id, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_is_on = False
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_light.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/light.py tests/test_light.py
git commit -m "feat: HubitatLight entity platform"
```

---

### Task 10: binary_sensor.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/binary_sensor.py`
- Create: `tests/test_binary_sensor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_binary_sensor.py
from unittest.mock import MagicMock
import pytest

MOTION = {
    "id": "10", "name": "Hall Motion", "label": "Hall Motion",
    "type": "Motion Sensor", "capabilities": ["MotionSensor"],
    "attributes": [{"name": "motion", "currentValue": "active", "dataType": "ENUM"}],
}
CONTACT = {
    "id": "11", "name": "Front Door", "label": "Front Door",
    "type": "Contact Sensor", "capabilities": ["ContactSensor"],
    "attributes": [{"name": "contact", "currentValue": "closed", "dataType": "ENUM"}],
}
WATER = {
    "id": "12", "name": "Basement Leak", "label": "Basement Leak",
    "type": "Water Sensor", "capabilities": ["WaterSensor"],
    "attributes": [{"name": "water", "currentValue": "dry", "dataType": "ENUM"}],
}
SMOKE = {
    "id": "13", "name": "Kitchen Smoke", "label": "Kitchen Smoke",
    "type": "Smoke Detector", "capabilities": ["SmokeDetector"],
    "attributes": [{"name": "smoke", "currentValue": "clear", "dataType": "ENUM"}],
}


def make_coord(hass, device):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    coord = MagicMock(spec=HubitatCoordinator)
    coord.hass = hass
    coord.hubitat_devices = {device["id"]: device}
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_motion_active(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatMotionSensor
    s = HubitatMotionSensor(MOTION, make_coord(hass, MOTION))
    assert s.is_on is True


async def test_motion_inactive(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatMotionSensor
    d = {**MOTION, "attributes": [{"name": "motion", "currentValue": "inactive", "dataType": "ENUM"}]}
    s = HubitatMotionSensor(d, make_coord(hass, d))
    assert s.is_on is False


async def test_contact_closed(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatContactSensor
    s = HubitatContactSensor(CONTACT, make_coord(hass, CONTACT))
    assert s.is_on is False  # closed = not triggered


async def test_contact_open(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatContactSensor
    d = {**CONTACT, "attributes": [{"name": "contact", "currentValue": "open", "dataType": "ENUM"}]}
    s = HubitatContactSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_water_wet(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatWaterSensor
    d = {**WATER, "attributes": [{"name": "water", "currentValue": "wet", "dataType": "ENUM"}]}
    s = HubitatWaterSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_smoke_detected(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatSmokeSensor
    d = {**SMOKE, "attributes": [{"name": "smoke", "currentValue": "detected", "dataType": "ENUM"}]}
    s = HubitatSmokeSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_handle_event_motion(hass):
    from custom_components.ha_hubitat_bridge.binary_sensor import HubitatMotionSensor
    s = HubitatMotionSensor(MOTION, make_coord(hass, MOTION))
    s.hass = hass
    s.handle_event("motion", "inactive")
    assert s.is_on is False
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_binary_sensor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement binary_sensor.py**

```python
# custom_components/ha_hubitat_bridge/binary_sensor.py
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity

_CAP_MAP = {
    "MotionSensor": "HubitatMotionSensor",
    "ContactSensor": "HubitatContactSensor",
    "WaterSensor": "HubitatWaterSensor",
    "SmokeDetector": "HubitatSmokeSensor",
}


def _binary_sensor_entities(device: dict, coordinator: HubitatCoordinator) -> list:
    caps = device.get("capabilities", [])
    entities = []
    if "MotionSensor" in caps:
        entities.append(HubitatMotionSensor(device, coordinator))
    if "ContactSensor" in caps:
        entities.append(HubitatContactSensor(device, coordinator))
    if "WaterSensor" in caps:
        entities.append(HubitatWaterSensor(device, coordinator))
    if "SmokeDetector" in caps:
        entities.append(HubitatSmokeSensor(device, coordinator))
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for d in coordinator.hubitat_devices.values():
        entities.extend(_binary_sensor_entities(d, coordinator))
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        new = _binary_sensor_entities(device, coordinator)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatMotionSensor(HubitatEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_motion"
        self._attr_is_on = self._get_attr("motion") == "active"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "motion":
            self._attr_is_on = value == "active"
            self.async_write_ha_state()


class HubitatContactSensor(HubitatEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_contact"
        self._attr_is_on = self._get_attr("contact") == "open"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "contact":
            self._attr_is_on = value == "open"
            self.async_write_ha_state()


class HubitatWaterSensor(HubitatEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.MOISTURE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_water"
        self._attr_is_on = self._get_attr("water") == "wet"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "water":
            self._attr_is_on = value == "wet"
            self.async_write_ha_state()


class HubitatSmokeSensor(HubitatEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.SMOKE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_smoke"
        self._attr_is_on = self._get_attr("smoke") == "detected"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "smoke":
            self._attr_is_on = value == "detected"
            self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_binary_sensor.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/binary_sensor.py tests/test_binary_sensor.py
git commit -m "feat: HubitatBinarySensor entities (motion, contact, water, smoke)"
```

---

### Task 11: sensor.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/sensor.py`
- Create: `tests/test_sensor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_sensor.py
from unittest.mock import MagicMock
import pytest
from homeassistant.components.sensor import SensorDeviceClass

TEMP_DEVICE = {
    "id": "20", "name": "Hallway Temp", "label": "Hallway Temp",
    "type": "Temp Sensor", "capabilities": ["TemperatureMeasurement"],
    "attributes": [{"name": "temperature", "currentValue": 21.5, "dataType": "NUMBER"}],
}
HUMIDITY_DEVICE = {
    "id": "21", "name": "Bath Humidity", "label": "Bath Humidity",
    "type": "Humidity Sensor", "capabilities": ["RelativeHumidityMeasurement"],
    "attributes": [{"name": "humidity", "currentValue": 65.0, "dataType": "NUMBER"}],
}
LUX_DEVICE = {
    "id": "22", "name": "Living Lux", "label": "Living Lux",
    "type": "Lux Sensor", "capabilities": ["IlluminanceMeasurement"],
    "attributes": [{"name": "illuminance", "currentValue": 300, "dataType": "NUMBER"}],
}
POWER_DEVICE = {
    "id": "23", "name": "Plug Power", "label": "Plug Power",
    "type": "Power Meter", "capabilities": ["PowerMeter"],
    "attributes": [{"name": "power", "currentValue": 45.2, "dataType": "NUMBER"}],
}


def make_coord(hass, device):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {device["id"]: device}
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_temperature_value(hass):
    from custom_components.ha_hubitat_bridge.sensor import HubitatTemperatureSensor
    s = HubitatTemperatureSensor(TEMP_DEVICE, make_coord(hass, TEMP_DEVICE))
    assert s.native_value == 21.5
    assert s.device_class == SensorDeviceClass.TEMPERATURE


async def test_humidity_value(hass):
    from custom_components.ha_hubitat_bridge.sensor import HubitatHumiditySensor
    s = HubitatHumiditySensor(HUMIDITY_DEVICE, make_coord(hass, HUMIDITY_DEVICE))
    assert s.native_value == 65.0


async def test_illuminance_value(hass):
    from custom_components.ha_hubitat_bridge.sensor import HubitatIlluminanceSensor
    s = HubitatIlluminanceSensor(LUX_DEVICE, make_coord(hass, LUX_DEVICE))
    assert s.native_value == 300.0


async def test_power_value(hass):
    from custom_components.ha_hubitat_bridge.sensor import HubitatPowerSensor
    s = HubitatPowerSensor(POWER_DEVICE, make_coord(hass, POWER_DEVICE))
    assert s.native_value == 45.2


async def test_handle_event_temperature(hass):
    from custom_components.ha_hubitat_bridge.sensor import HubitatTemperatureSensor
    s = HubitatTemperatureSensor(TEMP_DEVICE, make_coord(hass, TEMP_DEVICE))
    s.hass = hass
    s.handle_event("temperature", "22.1")
    assert s.native_value == 22.1
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_sensor.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement sensor.py**

```python
# custom_components/ha_hubitat_bridge/sensor.py
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfTemperature, PERCENTAGE, LIGHT_LUX
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _sensor_entities(device: dict, coordinator: HubitatCoordinator) -> list:
    caps = device.get("capabilities", [])
    entities = []
    if "TemperatureMeasurement" in caps:
        entities.append(HubitatTemperatureSensor(device, coordinator))
    if "RelativeHumidityMeasurement" in caps:
        entities.append(HubitatHumiditySensor(device, coordinator))
    if "IlluminanceMeasurement" in caps:
        entities.append(HubitatIlluminanceSensor(device, coordinator))
    if "PowerMeter" in caps:
        entities.append(HubitatPowerSensor(device, coordinator))
    return entities


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = []
    for d in coordinator.hubitat_devices.values():
        entities.extend(_sensor_entities(d, coordinator))
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        new = _sensor_entities(device, coordinator)
        if new:
            async_add_entities(new)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class _HubitatNumericSensor(HubitatEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _hubitat_attribute: str = ""

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        raw = self._get_attr(self._hubitat_attribute)
        self._attr_native_value = float(raw) if raw is not None else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == self._hubitat_attribute:
            try:
                self._attr_native_value = float(value)
            except ValueError:
                pass
            self.async_write_ha_state()


class HubitatTemperatureSensor(_HubitatNumericSensor):
    _hubitat_attribute = "temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_temperature"


class HubitatHumiditySensor(_HubitatNumericSensor):
    _hubitat_attribute = "humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_humidity"


class HubitatIlluminanceSensor(_HubitatNumericSensor):
    _hubitat_attribute = "illuminance"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_illuminance"


class HubitatPowerSensor(_HubitatNumericSensor):
    _hubitat_attribute = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT

    def __init__(self, device, coordinator):
        super().__init__(device, coordinator)
        self._attr_unique_id = f"hubitat_{self._device_id}_power"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_sensor.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/sensor.py tests/test_sensor.py
git commit -m "feat: HubitatSensor entities (temperature, humidity, illuminance, power)"
```

---

### Task 12: lock.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/lock.py`
- Create: `tests/test_lock.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_lock.py
from unittest.mock import AsyncMock, MagicMock
import pytest

LOCK_DEVICE = {
    "id": "30", "name": "Front Lock", "label": "Front Lock",
    "type": "Z-Wave Lock", "capabilities": ["Lock"],
    "attributes": [{"name": "lock", "currentValue": "locked", "dataType": "ENUM"}],
}


@pytest.fixture
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {"30": LOCK_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_initially_locked(coordinator):
    from custom_components.ha_hubitat_bridge.lock import HubitatLock
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    assert lk.is_locked is True


async def test_handle_event_unlocked(hass, coordinator):
    from custom_components.ha_hubitat_bridge.lock import HubitatLock
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    lk.handle_event("lock", "unlocked")
    assert lk.is_locked is False


async def test_lock_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.lock import HubitatLock
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    await lk.async_lock()
    coordinator.maker_client.send_command.assert_called_once_with("30", "lock")


async def test_unlock_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.lock import HubitatLock
    lk = HubitatLock(LOCK_DEVICE, coordinator)
    lk.hass = hass
    await lk.async_unlock()
    coordinator.maker_client.send_command.assert_called_once_with("30", "unlock")
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_lock.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement lock.py**

```python
# custom_components/ha_hubitat_bridge/lock.py
from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_lock(device: dict) -> bool:
    return "Lock" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatLock(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_lock(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_lock(device):
            async_add_entities([HubitatLock(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatLock(HubitatEntity, LockEntity):
    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_locked = self._get_attr("lock") == "locked"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "lock":
            self._attr_is_locked = value == "locked"
            self.async_write_ha_state()

    async def async_lock(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "lock")
        self._attr_is_locked = True
        self.async_write_ha_state()

    async def async_unlock(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "unlock")
        self._attr_is_locked = False
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_lock.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/lock.py tests/test_lock.py
git commit -m "feat: HubitatLock entity platform"
```

---

### Task 13: cover.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/cover.py`
- Create: `tests/test_cover.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cover.py
from unittest.mock import AsyncMock, MagicMock
import pytest

COVER_DEVICE = {
    "id": "40", "name": "Garage Door", "label": "Garage Door",
    "type": "Garage Door", "capabilities": ["GarageDoorControl"],
    "attributes": [{"name": "door", "currentValue": "closed", "dataType": "ENUM"}],
}


@pytest.fixture
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {"40": COVER_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_initially_closed(coordinator):
    from custom_components.ha_hubitat_bridge.cover import HubitatCover
    cv = HubitatCover(COVER_DEVICE, coordinator)
    assert cv.is_closed is True


async def test_handle_event_open(hass, coordinator):
    from custom_components.ha_hubitat_bridge.cover import HubitatCover
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    cv.handle_event("door", "open")
    assert cv.is_closed is False


async def test_open_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.cover import HubitatCover
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    await cv.async_open_cover()
    coordinator.maker_client.send_command.assert_called_once_with("40", "open")


async def test_close_command(hass, coordinator):
    from custom_components.ha_hubitat_bridge.cover import HubitatCover
    cv = HubitatCover(COVER_DEVICE, coordinator)
    cv.hass = hass
    await cv.async_close_cover()
    coordinator.maker_client.send_command.assert_called_once_with("40", "close")
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_cover.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement cover.py**

```python
# custom_components/ha_hubitat_bridge/cover.py
from __future__ import annotations

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


def _is_cover(device: dict) -> bool:
    return "GarageDoorControl" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatCover(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_cover(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_cover(device):
            async_add_entities([HubitatCover(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatCover(HubitatEntity, CoverEntity):
    _attr_device_class = CoverDeviceClass.GARAGE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_closed = self._get_attr("door") == "closed"

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "door":
            self._attr_is_closed = value == "closed"
            self.async_write_ha_state()

    async def async_open_cover(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "open")
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "close")
        self._attr_is_closed = True
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cover.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/cover.py tests/test_cover.py
git commit -m "feat: HubitatCover entity platform"
```

---

### Task 14: climate.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/climate.py`
- Create: `tests/test_climate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_climate.py
from unittest.mock import AsyncMock, MagicMock
import pytest
from homeassistant.components.climate import HVACMode

CLIMATE_DEVICE = {
    "id": "50", "name": "Hallway Thermostat", "label": "Hallway Thermostat",
    "type": "Z-Wave Thermostat", "capabilities": ["Thermostat"],
    "attributes": [
        {"name": "thermostatMode", "currentValue": "cool", "dataType": "ENUM"},
        {"name": "temperature", "currentValue": 22.0, "dataType": "NUMBER"},
        {"name": "coolingSetpoint", "currentValue": 24.0, "dataType": "NUMBER"},
        {"name": "heatingSetpoint", "currentValue": 19.0, "dataType": "NUMBER"},
    ],
}


@pytest.fixture
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {"50": CLIMATE_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_hvac_mode(coordinator):
    from custom_components.ha_hubitat_bridge.climate import HubitatClimate
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    assert cl.hvac_mode == HVACMode.COOL


async def test_current_temperature(coordinator):
    from custom_components.ha_hubitat_bridge.climate import HubitatClimate
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    assert cl.current_temperature == 22.0


async def test_handle_event_mode(hass, coordinator):
    from custom_components.ha_hubitat_bridge.climate import HubitatClimate
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    cl.handle_event("thermostatMode", "heat")
    assert cl.hvac_mode == HVACMode.HEAT


async def test_set_hvac_mode(hass, coordinator):
    from custom_components.ha_hubitat_bridge.climate import HubitatClimate
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    await cl.async_set_hvac_mode(HVACMode.OFF)
    coordinator.maker_client.send_command.assert_called_once_with("50", "setThermostatMode", "off")


async def test_set_temperature(hass, coordinator):
    from custom_components.ha_hubitat_bridge.climate import HubitatClimate
    cl = HubitatClimate(CLIMATE_DEVICE, coordinator)
    cl.hass = hass
    await cl.async_set_temperature(temperature=25.0)
    coordinator.maker_client.send_command.assert_any_call("50", "setCoolingSetpoint", "25.0")
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_climate.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement climate.py**

```python
# custom_components/ha_hubitat_bridge/climate.py
from __future__ import annotations

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity

_HUBITAT_TO_HA_MODE = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "auto": HVACMode.HEAT_COOL,
    "off": HVACMode.OFF,
    "emergency heat": HVACMode.HEAT,
}
_HA_TO_HUBITAT_MODE = {v: k for k, v in _HUBITAT_TO_HA_MODE.items() if k != "emergency heat"}


def _is_climate(device: dict) -> bool:
    return "Thermostat" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatClimate(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_climate(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_climate(device):
            async_add_entities([HubitatClimate(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatClimate(HubitatEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        raw_mode = self._get_attr("thermostatMode") or "off"
        self._attr_hvac_mode = _HUBITAT_TO_HA_MODE.get(raw_mode, HVACMode.OFF)
        temp = self._get_attr("temperature")
        self._attr_current_temperature = float(temp) if temp else None
        cool = self._get_attr("coolingSetpoint")
        heat = self._get_attr("heatingSetpoint")
        self._attr_target_temperature_high = float(cool) if cool else None
        self._attr_target_temperature_low = float(heat) if heat else None
        self._attr_target_temperature = float(cool) if cool else None

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "thermostatMode":
            self._attr_hvac_mode = _HUBITAT_TO_HA_MODE.get(value, HVACMode.OFF)
        elif attribute == "temperature":
            self._attr_current_temperature = float(value)
        elif attribute == "coolingSetpoint":
            self._attr_target_temperature_high = float(value)
            self._attr_target_temperature = float(value)
        elif attribute == "heatingSetpoint":
            self._attr_target_temperature_low = float(value)
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        hubitat_mode = _HA_TO_HUBITAT_MODE.get(hvac_mode, "off")
        await self._coordinator.maker_client.send_command(self._device_id, "setThermostatMode", hubitat_mode)
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        if temp is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setCoolingSetpoint", str(temp))
            self._attr_target_temperature = temp
        if high is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setCoolingSetpoint", str(high))
            self._attr_target_temperature_high = high
        if low is not None:
            await self._coordinator.maker_client.send_command(self._device_id, "setHeatingSetpoint", str(low))
            self._attr_target_temperature_low = low
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_climate.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add custom_components/ha_hubitat_bridge/climate.py tests/test_climate.py
git commit -m "feat: HubitatClimate entity platform"
```

---

### Task 15: fan.py

**Files:**
- Create: `custom_components/ha_hubitat_bridge/fan.py`
- Create: `tests/test_fan.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fan.py
from unittest.mock import AsyncMock, MagicMock
import pytest

FAN_DEVICE = {
    "id": "60", "name": "Bedroom Fan", "label": "Bedroom Fan",
    "type": "Fan Controller", "capabilities": ["FanControl"],
    "attributes": [
        {"name": "switch", "currentValue": "on", "dataType": "ENUM"},
        {"name": "speed", "currentValue": "medium", "dataType": "ENUM"},
    ],
}


@pytest.fixture
def coordinator(hass):
    from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator
    c = MagicMock(spec=HubitatCoordinator)
    c.hass = hass
    c.hubitat_devices = {"60": FAN_DEVICE}
    c.maker_client = AsyncMock()
    c.maker_client.send_command = AsyncMock(return_value={"result": "ok"})
    c.register_entity = MagicMock()
    c.unregister_entity = MagicMock()
    return c


async def test_fan_is_on(coordinator):
    from custom_components.ha_hubitat_bridge.fan import HubitatFan
    f = HubitatFan(FAN_DEVICE, coordinator)
    assert f.is_on is True


async def test_handle_event_off(hass, coordinator):
    from custom_components.ha_hubitat_bridge.fan import HubitatFan
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    f.handle_event("switch", "off")
    assert f.is_on is False


async def test_turn_on(hass, coordinator):
    from custom_components.ha_hubitat_bridge.fan import HubitatFan
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    await f.async_turn_on()
    coordinator.maker_client.send_command.assert_called_with("60", "on")


async def test_turn_off(hass, coordinator):
    from custom_components.ha_hubitat_bridge.fan import HubitatFan
    f = HubitatFan(FAN_DEVICE, coordinator)
    f.hass = hass
    await f.async_turn_off()
    coordinator.maker_client.send_command.assert_called_with("60", "off")
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_fan.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement fan.py**

```python
# custom_components/ha_hubitat_bridge/fan.py
from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity

_SPEED_TO_PCT = {"low": 33, "medium-low": 50, "medium": 66, "high": 100}
_PCT_TO_SPEED = {33: "low", 50: "medium-low", 66: "medium", 100: "high"}


def _is_fan(device: dict) -> bool:
    return "FanControl" in device.get("capabilities", [])


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HubitatCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities = [HubitatFan(d, coordinator) for d in coordinator.hubitat_devices.values() if _is_fan(d)]
    async_add_entities(entities)

    async def _handle_new(device: dict) -> None:
        if _is_fan(device):
            async_add_entities([HubitatFan(device, coordinator)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_DEVICE.format(entry_id=entry.entry_id), _handle_new)
    )


class HubitatFan(HubitatEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED

    def __init__(self, device: dict, coordinator: HubitatCoordinator) -> None:
        super().__init__(device, coordinator)
        self._attr_is_on = self._get_attr("switch") == "on"
        speed = self._get_attr("speed")
        self._attr_percentage = _SPEED_TO_PCT.get(speed, 0) if speed else 0

    def handle_event(self, attribute: str, value: str) -> None:
        if attribute == "switch":
            self._attr_is_on = value == "on"
        elif attribute == "speed":
            self._attr_percentage = _SPEED_TO_PCT.get(value, 0)
        self.async_write_ha_state()

    async def async_turn_on(self, percentage: int | None = None, **kwargs) -> None:
        if percentage is not None:
            await self.async_set_percentage(percentage)
        else:
            await self._coordinator.maker_client.send_command(self._device_id, "on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self._coordinator.maker_client.send_command(self._device_id, "off")
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        # Find closest speed string
        speed = min(_PCT_TO_SPEED, key=lambda p: abs(p - percentage))
        await self._coordinator.maker_client.send_command(self._device_id, "setSpeed", _PCT_TO_SPEED[speed])
        self._attr_percentage = percentage
        self.async_write_ha_state()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_fan.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run full test suite — all Hubitat→HA tasks complete**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ha_hubitat_bridge/fan.py tests/test_fan.py
git commit -m "feat: HubitatFan entity platform — Hubitat→HA direction complete"
```

---

### Task 16: HAToHubitat — HA→Hubitat sync

**Files:**
- Modify: `custom_components/ha_hubitat_bridge/ha_to_hubitat.py` (replace stub with full implementation)
- Create: `tests/test_ha_to_hubitat.py`

- [ ] **Step 1: Write failing tests**

```python
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

    # Simulate entity registry entry
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
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_ha_to_hubitat.py -v
```

Expected: ImportError or AttributeError from the stub.

- [ ] **Step 3: Replace ha_to_hubitat.py stub with full implementation**

```python
# custom_components/ha_hubitat_bridge/ha_to_hubitat.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    HA_DOMAIN_TO_DRIVER,
    BINARY_SENSOR_CLASS_TO_DRIVER,
    SENSOR_CLASS_TO_DRIVER,
    IGNORE_LABEL,
    MIRROR_DOMAINS,
)
from .entity_map import EntityMap
from .hubitat_client import HubitatMakerClient, HubitatWebClient

_LOGGER = logging.getLogger(__name__)


def _qualifies(entity_id: str, er_entry) -> bool:
    """Return True if this entity should be mirrored to Hubitat."""
    domain = entity_id.split(".")[0]
    if domain not in MIRROR_DOMAINS:
        return False
    if er_entry is None:
        return False
    if er_entry.entity_category is not None:
        return False
    if er_entry.platform == DOMAIN:
        return False
    if IGNORE_LABEL in (er_entry.labels or set()):
        return False
    return True


def _driver_for(entity_id: str, state: State) -> str:
    """Map an HA entity to the appropriate Hubitat virtual driver name."""
    domain = entity_id.split(".")[0]
    device_class = state.attributes.get("device_class")

    if domain == "binary_sensor":
        return BINARY_SENSOR_CLASS_TO_DRIVER.get(device_class, BINARY_SENSOR_CLASS_TO_DRIVER[None])
    if domain == "sensor":
        return SENSOR_CLASS_TO_DRIVER.get(device_class, SENSOR_CLASS_TO_DRIVER[None])
    if domain == "light":
        # If brightness supported → Virtual Dimmer
        if state.attributes.get("supported_color_modes") or state.attributes.get("brightness") is not None:
            return "Virtual Dimmer"
        return "Virtual Switch"
    return HA_DOMAIN_TO_DRIVER.get(domain, "Virtual Switch")


def _command_for(entity_id: str, state: State) -> tuple[str, str | None] | None:
    """
    Return (command, optional_value) to send to Hubitat for this state.
    Returns None if no command applies.
    """
    domain = entity_id.split(".")[0]
    s = state.state

    if domain in ("switch", "input_boolean", "media_player", "vacuum"):
        return ("on", None) if s == "on" else ("off", None)

    if domain == "light":
        if s == "off":
            return ("off", None)
        brightness = state.attributes.get("brightness")
        if brightness is not None:
            level = str(round(brightness / 255 * 100))
            return ("setLevel", level)
        return ("on", None)

    if domain == "lock":
        return ("lock", None) if s == "locked" else ("unlock", None)

    if domain == "cover":
        return ("open", None) if s == "open" else ("close", None)

    if domain == "binary_sensor":
        device_class = state.attributes.get("device_class")
        if device_class == "motion":
            return ("active", None) if s == "on" else ("inactive", None)
        if device_class == "moisture":
            return ("wet", None) if s == "on" else ("dry", None)
        return ("open", None) if s == "on" else ("close", None)

    if domain == "sensor":
        try:
            val = float(s)
        except (ValueError, TypeError):
            return None
        device_class = state.attributes.get("device_class")
        cmd_map = {
            "temperature": "setTemperature",
            "humidity": "setHumidity",
            "illuminance": "setIlluminance",
        }
        cmd = cmd_map.get(device_class, "setValue")
        return (cmd, str(val))

    if domain == "climate":
        hvac = s  # off, cool, heat, heat_cool
        hubitat_mode = {"heat_cool": "auto"}.get(hvac, hvac)
        return ("setThermostatMode", hubitat_mode)

    if domain == "fan":
        return ("on", None) if s == "on" else ("off", None)

    return None


class HAToHubitat:
    """Listens to HA state_changed events and mirrors qualifying entities to Hubitat virtual devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        maker_client: HubitatMakerClient,
        web_client: HubitatWebClient,
        entity_map: EntityMap,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._maker_client = maker_client
        self._web_client = web_client
        self._entity_map = entity_map
        self._unsub = None

    async def async_setup(self) -> None:
        from homeassistant.core import EVENT_STATE_CHANGED
        self._unsub = self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._on_state_changed)
        self._entry.async_on_unload(self.async_teardown)

    async def async_teardown(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _on_state_changed(self, event: Event) -> None:
        entity_id: str = event.data["entity_id"]
        new_state: State | None = event.data.get("new_state")
        if new_state is None:
            return
        self.hass.async_create_task(self._handle_state_changed(entity_id, new_state))

    async def _handle_state_changed(self, entity_id: str, state: State) -> None:
        registry = er.async_get(self.hass)
        er_entry = registry.async_get(entity_id)
        if not _qualifies(entity_id, er_entry):
            return

        if not self._entity_map.has(entity_id):
            await self._create_virtual_device(entity_id, state)

        await self._sync_state(entity_id, state)

    async def _create_virtual_device(self, entity_id: str, state: State) -> None:
        friendly_name = state.attributes.get("friendly_name", entity_id)
        driver = _driver_for(entity_id, state)
        _LOGGER.info("Creating Hubitat virtual device '%s' (%s) for %s", friendly_name, driver, entity_id)

        device_id = await self._web_client.async_create_virtual_device(friendly_name, driver)
        if device_id is None:
            self.hass.components.persistent_notification.async_create(
                f"Hubitat Bridge: Could not create virtual device for **{friendly_name}**. "
                f"Check Hubitat connection at {self._web_client._hub_url}.",
                title="Hubitat Bridge Error",
                notification_id=f"hab_create_fail_{entity_id}",
            )
            return

        self._entity_map.put(entity_id, device_id)
        await self._entity_map.async_save()

    async def _sync_state(self, entity_id: str, state: State) -> None:
        device_id = self._entity_map.get(entity_id)
        if device_id is None:
            return

        cmd = _command_for(entity_id, state)
        if cmd is None:
            return

        command, value = cmd
        try:
            if value is not None:
                await self._maker_client.send_command(device_id, command, value)
            else:
                await self._maker_client.send_command(device_id, command)
        except Exception as exc:
            _LOGGER.error("Failed to sync %s → Hubitat device %s: %s", entity_id, device_id, exc)
            self.hass.components.persistent_notification.async_create(
                f"Hubitat Bridge: Failed to sync **{entity_id}** to Hubitat. Error: {exc}",
                title="Hubitat Bridge Error",
                notification_id=f"hab_sync_fail_{entity_id}",
            )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_ha_to_hubitat.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/ha_hubitat_bridge/ha_to_hubitat.py tests/test_ha_to_hubitat.py
git commit -m "feat: HAToHubitat — HA→Hubitat sync, filter, virtual device creation, command dispatch"
```

---

### Task 17: HACS distribution polish

**Files:**
- Modify: `custom_components/ha_hubitat_bridge/manifest.json` (final version)
- Modify: `hacs.json` (final version)
- Create: `CHANGELOG.md`
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

```
__pycache__/
*.pyc
.pytest_cache/
.env
*.egg-info/
dist/
.mypy_cache/
```

- [ ] **Step 2: Update manifest.json with documentation URL placeholder**

Update `custom_components/ha_hubitat_bridge/manifest.json` — replace `YOUR_USERNAME` with actual GitHub username:

```json
{
  "domain": "ha_hubitat_bridge",
  "name": "Hubitat Bridge",
  "version": "0.1.0",
  "config_flow": true,
  "documentation": "https://github.com/tekchip/ha-hubitat-bridge",
  "issue_tracker": "https://github.com/tekchip/ha-hubitat-bridge/issues",
  "iot_class": "local_push",
  "requirements": [],
  "codeowners": ["@tekchip"]
}
```

- [ ] **Step 3: Update hacs.json**

```json
{
  "name": "Hubitat Bridge",
  "description": "Bidirectional device mirroring between Home Assistant and Hubitat Elevation. Devices added to either system automatically appear in the other.",
  "content_in_root": false,
  "homeassistant": "2024.1.0",
  "iot_class": "local_push"
}
```

- [ ] **Step 4: Create CHANGELOG.md**

```markdown
# Changelog

## 0.1.0 — 2026-04-06

### Added
- Bidirectional device mirroring between Home Assistant and Hubitat Elevation
- Config flow UI for Hubitat connection setup (URL, Maker API App ID, token, credentials)
- Hubitat → HA: switch, light (dimmer), binary_sensor (motion/contact/water/smoke), sensor (temperature/humidity/illuminance/power), lock, cover, climate, fan
- HA → Hubitat: automatic virtual device creation for qualifying HA entities
- Real-time Hubitat → HA sync via Maker API webhook
- 60-second polling for new Hubitat device discovery
- Automatic HA → Hubitat state sync via state_changed listener
- Feedback loop prevention (Hubitat-sourced entities excluded from HA→Hubitat sync)
- `hubitat-ignore` label escape hatch for opt-out
- Graceful error handling with `persistent_notification` alerts
- Retry with exponential backoff on all Hubitat API calls
```

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: all tests pass, 0 failures.

- [ ] **Step 6: Final commit**

```bash
git add .gitignore CHANGELOG.md custom_components/ha_hubitat_bridge/manifest.json hacs.json
git commit -m "feat: HACS distribution files, changelog, v0.1.0"
```

---

## Post-Implementation: Live Testing Checklist

After deploying to your HA instance (`cp -r custom_components/ha_hubitat_bridge /path/to/homeassistant/custom_components/`):

1. Restart HA. Navigate to **Settings → Integrations → Add Integration → Hubitat Bridge**
2. Enter: `http://10.10.10.7`, App ID `150`, token from credentials.md, username `brock`, password from credentials.md
3. Confirm Hubitat devices appear in HA (check **Developer Tools → States** for `switch.*`, `light.*`, etc. with `unique_id` starting `hubitat_`)
4. Toggle a Hubitat device from HA — confirm it changes state in Hubitat web UI
5. Toggle a Hubitat device from Hubitat web UI — confirm the HA entity updates within seconds
6. Turn on a Thread or HA-only device — confirm a virtual device appears in Hubitat within 60s (or immediately on the next state change)
7. Add a new device to Hubitat's Maker API app — confirm it appears in HA within 60s
8. Check **Settings → Notifications** for any Hubitat Bridge error notifications

> **Important:** If virtual device creation fails (step 6), use browser DevTools to capture the actual POST request when manually adding a virtual device at `http://10.10.10.7` → Devices → Add Virtual Device. Compare field names against `HubitatWebClient.async_create_virtual_device` and update accordingly. This endpoint is reverse-engineered and may need adjustment on your specific Hubitat firmware version.
