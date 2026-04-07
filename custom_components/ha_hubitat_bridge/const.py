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
