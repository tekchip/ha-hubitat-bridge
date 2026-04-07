from __future__ import annotations

import asyncio
import logging
import urllib.parse
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

_RETRY_DELAYS = (0, 2, 8)  # seconds before attempt 1, 2, 3


async def _with_retry(coro_factory, label: str) -> Any:
    """Run coro_factory() up to 3 times with exponential backoff. Re-raises on final failure.

    Does not retry on HTTP 4xx/5xx errors — they won't resolve by retrying.
    Only retries on connection/timeout errors.
    """
    last_exc: Exception | None = None
    for delay in _RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            return await coro_factory()
        except aiohttp.ClientResponseError as exc:
            # Don't retry HTTP errors (4xx/5xx) — they won't resolve by retrying
            raise
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


class HubitatWebClient:
    """
    Authenticated client for Hubitat's web UI.
    Used exclusively for creating virtual devices, which the Maker API cannot do.

    Manages its own aiohttp session with CookieJar(unsafe=True) because Hubitat
    runs on an IP address and aiohttp's default jar silently drops cookies from IPs.
    Call async_close() when done (or register it with entry.async_on_unload).
    """

    def __init__(
        self,
        hub_url: str,
        username: str,
        password: str,
    ) -> None:
        self._hub_url = hub_url.rstrip("/")
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._authenticated = False
        self._driver_map: dict[str, int] = {}  # driver name → Hubitat numeric ID

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._session

    async def async_close(self) -> None:
        """Close the underlying HTTP session. Must be called on integration unload."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def async_login(self) -> bool:
        """POST credentials to /login. Returns True if Hubitat redirects away from /login."""
        url = f"{self._hub_url}/login"
        data = {"username": self._username, "password": self._password, "submit": "Login"}
        try:
            async with self._get_session().post(
                url, data=data, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                # Successful login: Hubitat issues a 302 redirect away from /login
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    self._authenticated = bool(location) and not location.rstrip("/").endswith("/login")
                else:
                    self._authenticated = False
                return self._authenticated
        except Exception as exc:
            _LOGGER.error("Hubitat web login failed: %s", exc)
            self._authenticated = False
            return False

    async def _load_driver_map(self) -> None:
        """Fetch the full driver list from Hubitat and cache name→id mappings."""
        try:
            async with self._get_session().get(
                f"{self._hub_url}/driver/list/data",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                drivers = await resp.json(content_type=None)
                self._driver_map = {
                    d["name"]: d["id"]
                    for d in drivers
                    if isinstance(d, dict) and "name" in d and "id" in d
                }
                _LOGGER.debug("Loaded %d Hubitat drivers", len(self._driver_map))
        except Exception as exc:
            _LOGGER.error("Failed to load Hubitat driver list: %s", exc)

    async def async_create_virtual_device(self, name: str, driver: str) -> str | None:
        """
        Create a virtual device on Hubitat and set its label.
        Returns the new Hubitat device ID string, or None on failure.

        Uses GET /device/createVirtual?deviceTypeId=<id> (numeric driver ID fetched
        from /driver/list/data), then GET /device/updateLabel to name the device.
        """
        if not self._authenticated:
            _LOGGER.debug("Not authenticated; logging in before creating virtual device")
            if not await self.async_login():
                _LOGGER.error("Login failed — cannot create virtual device '%s'", name)
                return None

        if not self._driver_map:
            await self._load_driver_map()

        driver_id = self._driver_map.get(driver)
        if driver_id is None:
            _LOGGER.error(
                "Unknown virtual driver '%s'. Available drivers: %s",
                driver, sorted(self._driver_map.keys()),
            )
            return None

        session = self._get_session()

        # Create the virtual device
        try:
            async with session.get(
                f"{self._hub_url}/device/createVirtual",
                params={"deviceTypeId": driver_id},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    if "login" in location:
                        _LOGGER.warning("Session expired creating virtual device '%s'", name)
                        self._authenticated = False
                    else:
                        _LOGGER.error(
                            "createVirtual for '%s': unexpected redirect to %r", name, location
                        )
                    return None
                result = await resp.json(content_type=None)
        except Exception as exc:
            _LOGGER.error("Failed to create virtual device '%s' (%s): %s", name, driver, exc)
            return None

        if not result.get("success"):
            _LOGGER.error("createVirtual returned failure for '%s': %s", name, result)
            return None

        device_id = result.get("deviceId")
        if device_id is None:
            _LOGGER.error("createVirtual returned no deviceId for '%s': %s", name, result)
            return None

        # Set the device label to the friendly name
        try:
            async with session.get(
                f"{self._hub_url}/device/updateLabel",
                params={"deviceId": device_id, "label": name},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                await resp.read()
        except Exception as exc:
            _LOGGER.warning("Created device %s but failed to set label '%s': %s", device_id, name, exc)

        return str(device_id)
