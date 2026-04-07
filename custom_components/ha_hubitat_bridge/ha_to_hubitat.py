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
from .hubitat_client import HubitatWebClient

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
        # Round to 2 decimal places — avoids absurdly long URL paths for floats
        return (cmd, str(round(val, 2)))

    if domain == "climate":
        hvac = s
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
        web_client: HubitatWebClient,
        entity_map: EntityMap,
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._web_client = web_client
        self._entity_map = entity_map
        self._unsub = None

    async def async_setup(self) -> None:
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
            # Skip sync on first creation — the Maker API needs a moment to register
            # the new virtual device. The next state change will trigger the sync.
            return

        await self._sync_state(entity_id, state)

    async def _create_virtual_device(self, entity_id: str, state: State) -> None:
        friendly_name = state.attributes.get("friendly_name", entity_id)
        driver = _driver_for(entity_id, state)
        _LOGGER.info("Creating Hubitat virtual device '%s' (%s) for %s", friendly_name, driver, entity_id)

        device_id = await self._web_client.async_create_virtual_device(friendly_name, driver)
        if device_id is None:
            from homeassistant.components.persistent_notification import async_create as pn_create
            pn_create(
                self.hass,
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
        ok = await self._web_client.async_send_command(device_id, command, value)
        if not ok:
            _LOGGER.error("Failed to sync %s → Hubitat device %s (%s)", entity_id, device_id, command)
