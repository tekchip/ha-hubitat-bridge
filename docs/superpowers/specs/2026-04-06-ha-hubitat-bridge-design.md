# HA Hubitat Bridge — Design Spec
_Date: 2026-04-06_

## Goal

A single HACS-installable Home Assistant custom integration (`ha_hubitat_bridge`) that provides full bidirectional device mirroring between Home Assistant and Hubitat Elevation. Any device on either system can be used in automations on either system. New devices are discovered automatically — no manual configuration per device.

## Background & Motivation

- The household is deeply integrated in Hubitat for automations and family UI
- HA has the only Thread radio, so a subset of devices can only reach Hubitat via HA
- Some integrations (media players, Thread devices, certain sensors) exist only in HA
- Both platforms must see all devices so automations can be written in either

## Architecture

Two sync directions, both managed by a single integration:

```
Hubitat (10.10.10.7)                      Home Assistant
┌──────────────────────┐                 ┌────────────────────────────┐
│  Real devices        │◄── webhook ────►│  ha_hubitat_bridge         │
│  Maker API (App 150) │                 │  - Hubitat→HA entities     │
│  Virtual devices ◄───┼── Maker API ───►│  - HA→Hubitat sync         │
└──────────────────────┘                 │  - Config flow UI          │
                                         │  - Error notifications     │
                                         └────────────────────────────┘
```

**Hubitat → HA:** Integration discovers Hubitat devices via Maker API, creates native HA entities, receives real-time state updates via Hubitat's event webhook. Falls back to 60s polling for missed events and new device discovery.

**HA → Hubitat:** Integration watches HA `state_changed` events, filters to qualifying entities, auto-creates Hubitat virtual devices, and syncs state changes via Maker API commands.

## Project Structure

```
custom_components/ha_hubitat_bridge/
  __init__.py              — async_setup_entry, coordinator, integration lifecycle
  config_flow.py           — ConfigFlow UI: URL, App ID, token; connection test
  manifest.json            — HA + HACS metadata, version, dependencies
  const.py                 — DOMAIN, domain allowlist, HA→Hubitat device type map, command map
  hubitat_client.py        — Maker API client + authenticated Hubitat web API (device creation)
  entity_map.py            — Persistent mapping: HA entity_id ↔ Hubitat device ID (.storage)
  ha_to_hubitat.py         — state_changed listener, virtual device creation, command dispatch
  hubitat_to_ha.py         — Maker API device fetch, webhook handler, entity registration
  switch.py                — HubitatSwitch, HubitatVirtualSwitch entities
  light.py                 — HubitatLight (dimmer support)
  sensor.py                — HubitatSensor (temp, humidity, illuminance, power, generic)
  binary_sensor.py         — HubitatBinarySensor (motion, contact, moisture, smoke)
  lock.py                  — HubitatLock
  cover.py                 — HubitatCover (garage door, shade)
  climate.py               — HubitatClimate (thermostat)
  fan.py                   — HubitatFan
  strings.json             — Config flow UI strings
  translations/en.json     — English translations
hacs.json                  — HACS repository metadata
```

## Config Flow (Setup UI)

Fields:
- **Hubitat Hub URL** — e.g. `http://10.10.10.7` (validated as reachable)
- **Maker API App ID** — integer, e.g. `150`
- **Access Token** — Maker API UUID token (used for device control and state queries)
- **Hub Username** — Hubitat web UI login (needed for virtual device creation)
- **Hub Password** — Hubitat web UI password (needed for virtual device creation)

On submit: calls `GET /apps/api/{app_id}/devices?access_token={token}` to validate Maker API access, and attempts a login to the Hubitat web UI to validate credentials. If both succeed, creates config entry and proceeds to setup. Re-configurable at any time via HA's integrations UI (handles IP/token/password changes).

## Hubitat → HA (hubitat_to_ha.py)

### Device Discovery
1. On `async_setup_entry`: fetch device list from `GET /apps/api/{id}/devices`
2. For each device, inspect its `capabilities` list to determine the HA platform
3. Register entities via `async_forward_entry_setups` for each platform
4. Re-poll every 60s for new devices; register any not yet seen

### Real-time Updates (Webhook)
1. Register an HA webhook: `webhook_id = f"ha_hubitat_bridge_{entry.entry_id}"`
2. Configure Hubitat Maker API event subscription to POST to `http://{HA_IP}:8123/api/webhook/{webhook_id}`
3. On incoming webhook event: parse `deviceId`, `name` (attribute), `value` → update matching entity state via `async_write_ha_state`
4. Webhook registration survives restarts (stored in config entry data)

### Hubitat Capability → HA Platform Mapping

| Hubitat capability | HA platform | Entity class |
|---|---|---|
| `Switch` | `switch` | HubitatSwitch |
| `SwitchLevel` (+ Switch) | `light` | HubitatLight |
| `MotionSensor` | `binary_sensor` | HubitatMotionSensor |
| `ContactSensor` | `binary_sensor` | HubitatContactSensor |
| `WaterSensor` | `binary_sensor` | HubitatWaterSensor |
| `SmokeDetector` | `binary_sensor` | HubitatSmokeSensor |
| `TemperatureMeasurement` | `sensor` | HubitatTemperatureSensor |
| `RelativeHumidityMeasurement` | `sensor` | HubitatHumiditySensor |
| `IlluminanceMeasurement` | `sensor` | HubitatIlluminanceSensor |
| `PowerMeter` | `sensor` | HubitatPowerSensor |
| `Lock` | `lock` | HubitatLock |
| `GarageDoorControl` | `cover` | HubitatCover |
| `Thermostat` | `climate` | HubitatClimate |
| `FanControl` | `fan` | HubitatFan |

Devices with multiple capabilities (e.g. `Switch` + `TemperatureMeasurement`) register entities on multiple platforms.

## HA → Hubitat (ha_to_hubitat.py)

### Entity Filter (automatic, no configuration)
An entity qualifies for mirroring if ALL of the following are true:
1. `entity_category` is `None` (primary entity, not diagnostic or config)
2. Domain is in the allowlist: `switch`, `light`, `binary_sensor`, `sensor`, `lock`, `cover`, `climate`, `fan`, `media_player`, `vacuum`, `input_boolean`
3. Entity's integration platform is NOT `ha_hubitat_bridge` (prevents feedback loop)
4. Entity does not have the label `hubitat-ignore` (opt-out escape hatch)

### Virtual Device Creation
When a qualifying entity has no Hubitat mirror yet:
1. Authenticate to Hubitat web UI (stored credentials in config entry)
2. POST to Hubitat's internal device creation endpoint with the appropriate virtual driver name
3. Add the new device to the Maker API app (so it appears in `/devices`)
4. Store `entity_id → hubitat_device_id` in persistent `.storage` map via `entity_map.py`

### HA Domain → Hubitat Virtual Driver Mapping

| HA domain / device class | Hubitat virtual driver |
|---|---|
| `switch`, `input_boolean` | Virtual Switch |
| `light` with brightness | Virtual Dimmer |
| `light` on/off only | Virtual Switch |
| `binary_sensor` motion | Virtual Motion Sensor |
| `binary_sensor` door/window/contact | Virtual Contact Sensor |
| `binary_sensor` moisture | Virtual Water Sensor |
| `binary_sensor` (other) | Virtual Contact Sensor |
| `sensor` temperature | Virtual Temperature Sensor |
| `sensor` humidity | Virtual Humidity Sensor |
| `sensor` illuminance | Virtual Illuminance Sensor |
| `lock` | Virtual Lock |
| `cover` | Virtual Garage Door Control |
| `climate` | Virtual Thermostat |
| `fan` | Virtual Fan Controller |
| `media_player`, `vacuum` | Virtual Switch (on/off only) |

### State Sync (Command Dispatch)
On `state_changed` for a mirrored entity, send the appropriate Maker API command:

| HA state / attribute | Hubitat command |
|---|---|
| `on` / `off` | `on()` / `off()` |
| brightness (light) | `setLevel(0-100)` |
| `locked` / `unlocked` | `lock()` / `unlock()` |
| `open` / `closed` | `open()` / `close()` |
| temperature attribute | `setTemperature(val)` |
| humidity attribute | `setHumidity(val)` |
| numeric sensor value | `setValue(val)` |
| HVAC mode / setpoint | `setThermostatMode()` / `setCoolingSetpoint()` / `setHeatingSetpoint()` |

## Error Handling & Notifications

### Retry Policy
All Hubitat API calls (Maker API and internal web API) use exponential backoff:
- Attempt 1: immediate
- Attempt 2: 2s delay
- Attempt 3: 8s delay
- After 3 failures: log error + fire `persistent_notification.create`

### Notification Messages
Notifications are specific and actionable:
- `"Hubitat Bridge: Could not create virtual device for {friendly_name}. Check Hubitat connection at {url}."`
- `"Hubitat Bridge: Lost connection to Hubitat. Retrying... (attempt {n})"`
- `"Hubitat Bridge: Unsupported device type '{domain}' for {entity_id} — skipped."`

### Non-blocking Guarantee
- All sync operations run in HA's async event loop; no blocking I/O on the main thread
- Failures are caught at the per-entity level — one bad device never blocks others
- Integration startup never blocks HA boot (uses `async_setup_entry` correctly)
- WebSocket/webhook reconnects automatically without user intervention

## Feedback Loop Prevention

Entities sourced from `ha_hubitat_bridge` are excluded from the HA→Hubitat filter. This means real Hubitat devices (which appear in HA via the integration) are never mirrored back to Hubitat as virtual devices. The check uses the entity registry's `platform` field.

## Persistence

- Config entry stores: Hubitat URL, App ID, Access Token, webhook ID, HA IP for webhook registration
- `.storage/ha_hubitat_bridge.json` stores: `entity_id → hubitat_device_id` map (written via `entity_map.py` using HA's `Store` helper)
- Webhook ID is stable across restarts (derived from `entry.entry_id`)

## HACS Distribution

- `hacs.json` at repo root declares `name`, `description`, `documentation`, `issue_tracker`
- `manifest.json` has `version`, `domain`, `requirements`, `iot_class: "local_push"`
- GitHub repo: `ha-hubitat-bridge` (this directory)
- Semantic versioning; changelog in `CHANGELOG.md`

## Hubitat → HA Control Path

Hubitat entities created in HA are fully controllable — not read-only. Each entity platform implements the appropriate HA service calls (`turn_on`, `turn_off`, `set_brightness`, `lock`, `unlock`, etc.) which dispatch the corresponding Maker API command to Hubitat in real time. This enables HA automations to control Hubitat devices directly.

## Out of Scope

- HA scenes or scripts mirrored to Hubitat
- Hubitat modes/rules mirrored to HA
- Any cloud-dependent path — all communication is local
