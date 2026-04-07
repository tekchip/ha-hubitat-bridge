# Hubitat Bridge

A [HACS](https://hacs.xyz)-installable Home Assistant custom integration that provides **full bidirectional device mirroring** between Home Assistant and [Hubitat Elevation](https://hubitat.com).

Devices on either system are automatically discoverable for automations on the other — no manual per-device configuration required.

## How it works

- **Hubitat → HA:** The integration discovers your Hubitat devices and creates native HA entities (switch, light, binary sensor, sensor, lock, cover, climate, fan). State changes on Hubitat are pushed to HA in real time via webhook, with 60-second polling as a fallback.
- **HA → Hubitat:** The integration watches for state changes on qualifying HA entities, automatically creates matching virtual devices in Hubitat, and keeps them in sync. This is especially useful for Thread devices and other integrations that only exist in HA.

## Prerequisites

### 1. Install and configure the Maker API app on Hubitat

The Maker API is a built-in Hubitat app that exposes your devices over a local REST API.

1. In Hubitat, go to **Apps → Add Built-In App → Maker API**
2. Under **"Allow Access to the following devices"**, check **every device** you want to appear in Home Assistant — if a device isn't checked here it will not sync
3. Enable **"Allow Access to all Devices"** (recommended) or select devices individually
4. Note your **App ID** from the URL bar (e.g. `http://hubitat.local/installedapp/configure/`**`150`**`/mainPage`)
5. Note your **Access Token** shown on the Maker API page

> **Tip:** You can verify which devices are exposed by visiting `http://<hubitat-ip>/apps/api/<app-id>/devices?access_token=<token>` in your browser. Only devices listed there will sync to HA.

### 2. Know your Hubitat web UI credentials

Virtual device creation (HA → Hubitat direction) requires logging into the Hubitat web UI. You'll need the username and password you use to log into your Hubitat hub.

## Installation

### Via HACS (recommended)

1. In Home Assistant, open **HACS → Integrations**
2. Click ⋮ → **Custom repositories**
3. Add `https://github.com/tekchip/ha-hubitat-bridge` with category **Integration**
4. Search for **Hubitat Bridge** and click **Download**
5. Restart Home Assistant

### Manual

Copy the `custom_components/ha_hubitat_bridge` folder to your HA `config/custom_components/` directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Integrations → Add Integration**
2. Search for **Hubitat Bridge**
3. Fill in the form:
   - **Hubitat Hub URL** — e.g. `http://10.10.10.7` (no trailing slash)
   - **Maker API App ID** — the number from the Maker API URL (e.g. `150`)
   - **Access Token** — from the Maker API configuration page
   - **Hub Username** — your Hubitat web UI login
   - **Hub Password** — your Hubitat web UI password
4. Click **Submit** — the integration validates both the Maker API and web credentials before saving

## Troubleshooting

### Devices are missing from Home Assistant

The most common cause is that the devices aren't added to the Maker API app.

1. In Hubitat, go to **Apps → Maker API**
2. Check that all desired devices are selected under **"Allow Access to the following devices"**
3. Verify by visiting `http://<hubitat-ip>/apps/api/<app-id>/devices?access_token=<token>` — only devices listed there will sync

New devices added to the Maker API are picked up automatically within 60 seconds without restarting HA.

### "Invalid credentials" error during setup

This means the Maker API connected successfully but the Hubitat web UI login failed. Double-check the username and password used to log into the Hubitat web interface.

### "Cannot connect" error during setup

HA cannot reach the Hubitat Maker API. Check:
- The hub URL is correct and reachable from HA (try it in a browser)
- The App ID and access token are correct

### Virtual devices aren't being created in Hubitat (HA → Hubitat direction)

Check **Settings → Notifications** in HA for any Hubitat Bridge error alerts. Virtual device creation requires the Hubitat web UI credentials to be correct and the hub to be reachable.

If creation fails, use browser DevTools to capture the exact POST request when manually adding a virtual device at **Hubitat web UI → Devices → Add Virtual Device** and open a GitHub issue with the field names observed.

### An entity isn't syncing to Hubitat

Entities are excluded from HA → Hubitat sync if any of the following are true:
- They are **diagnostic or configuration** entities (internal HA entities)
- They come from the **ha_hubitat_bridge** integration itself (prevents feedback loops)
- They have the **`hubitat-ignore`** label (opt-out escape hatch)
- Their domain is not in the supported list: `switch`, `light`, `binary_sensor`, `sensor`, `lock`, `cover`, `climate`, `fan`, `media_player`, `vacuum`, `input_boolean`

## Supported device types

### Hubitat → HA

| Hubitat capability | HA platform |
|---|---|
| `Switch` (without `SwitchLevel`) | `switch` |
| `SwitchLevel` | `light` (with brightness) |
| `MotionSensor` | `binary_sensor` (motion) |
| `ContactSensor` | `binary_sensor` (door) |
| `WaterSensor` | `binary_sensor` (moisture) |
| `SmokeDetector` | `binary_sensor` (smoke) |
| `TemperatureMeasurement` | `sensor` (temperature) |
| `RelativeHumidityMeasurement` | `sensor` (humidity) |
| `IlluminanceMeasurement` | `sensor` (illuminance) |
| `PowerMeter` | `sensor` (power) |
| `Lock` | `lock` |
| `GarageDoorControl` | `cover` |
| `Thermostat` | `climate` |
| `FanControl` | `fan` |

Devices with multiple capabilities create entities on multiple platforms.

### HA → Hubitat (virtual devices)

| HA domain | Hubitat virtual driver |
|---|---|
| `switch`, `input_boolean` | Virtual Switch |
| `light` with brightness | Virtual Dimmer |
| `light` on/off only | Virtual Switch |
| `binary_sensor` motion | Virtual Motion Sensor |
| `binary_sensor` door/window | Virtual Contact Sensor |
| `binary_sensor` moisture | Virtual Water Sensor |
| `sensor` temperature | Virtual Temperature Sensor |
| `sensor` humidity | Virtual Humidity Sensor |
| `lock` | Virtual Lock |
| `cover` | Virtual Garage Door Control |
| `climate` | Virtual Thermostat |
| `fan` | Virtual Fan Controller |
| `media_player`, `vacuum` | Virtual Switch (on/off only) |

## Opting out of HA → Hubitat sync

To prevent a specific HA entity from being mirrored to Hubitat, add the label **`hubitat-ignore`** to it in the HA entity registry (**Settings → Entities → [entity] → Labels**).
