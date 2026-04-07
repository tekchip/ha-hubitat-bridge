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
