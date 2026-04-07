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
