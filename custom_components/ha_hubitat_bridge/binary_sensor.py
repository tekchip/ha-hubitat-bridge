from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_DEVICE
from .hubitat_to_ha import HubitatCoordinator, HubitatEntity


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
