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
