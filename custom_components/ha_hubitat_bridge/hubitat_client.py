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
                url, data=data, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                # Hubitat redirects to /device/edit/{id} on success
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    if location.rstrip("/").endswith("/login"):
                        self._authenticated = False  # session expired
                        return None
                    if "/device/edit/" in location:
                        return location.split("/device/edit/")[-1].split("?")[0].strip()
                    # Fallback: scan response body for redirect hint
                    body = await resp.text()
                    match = re.search(r"/device/edit/(\d+)", body)
                    return match.group(1) if match else None
                return None  # non-redirect, non-error response with no usable ID
        except Exception as exc:
            _LOGGER.error("Failed to create virtual device '%s' (%s): %s", name, driver, exc)
            return None
