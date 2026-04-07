# tests/test_binary_sensor.py
from unittest.mock import MagicMock, patch
import pytest

from custom_components.ha_hubitat_bridge.binary_sensor import (
    HubitatMotionSensor,
    HubitatContactSensor,
    HubitatWaterSensor,
    HubitatSmokeSensor,
)
from custom_components.ha_hubitat_bridge.hubitat_to_ha import HubitatCoordinator

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
    coord = MagicMock(spec=HubitatCoordinator)
    coord.hass = hass
    coord.hubitat_devices = {device["id"]: device}
    coord.register_entity = MagicMock()
    coord.unregister_entity = MagicMock()
    return coord


async def test_motion_active(hass):
    s = HubitatMotionSensor(MOTION, make_coord(hass, MOTION))
    assert s.is_on is True


async def test_motion_inactive(hass):
    d = {**MOTION, "attributes": [{"name": "motion", "currentValue": "inactive", "dataType": "ENUM"}]}
    s = HubitatMotionSensor(d, make_coord(hass, d))
    assert s.is_on is False


async def test_contact_closed(hass):
    s = HubitatContactSensor(CONTACT, make_coord(hass, CONTACT))
    assert s.is_on is False  # closed = not triggered


async def test_contact_open(hass):
    d = {**CONTACT, "attributes": [{"name": "contact", "currentValue": "open", "dataType": "ENUM"}]}
    s = HubitatContactSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_water_wet(hass):
    d = {**WATER, "attributes": [{"name": "water", "currentValue": "wet", "dataType": "ENUM"}]}
    s = HubitatWaterSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_smoke_detected(hass):
    d = {**SMOKE, "attributes": [{"name": "smoke", "currentValue": "detected", "dataType": "ENUM"}]}
    s = HubitatSmokeSensor(d, make_coord(hass, d))
    assert s.is_on is True


async def test_handle_event_motion(hass):
    s = HubitatMotionSensor(MOTION, make_coord(hass, MOTION))
    s.hass = hass
    with patch.object(s, "async_write_ha_state"):
        s.handle_event("motion", "inactive")
    assert s.is_on is False
