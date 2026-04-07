# Changelog

## 0.1.0 — 2026-04-06

### Added
- Bidirectional device mirroring between Home Assistant and Hubitat Elevation
- Config flow UI for Hubitat connection setup (URL, Maker API App ID, token, credentials)
- Hubitat → HA: switch, light (dimmer), binary_sensor (motion/contact/water/smoke), sensor (temperature/humidity/illuminance/power), lock, cover, climate, fan
- HA → Hubitat: automatic virtual device creation for qualifying HA entities
- Real-time Hubitat → HA sync via Maker API webhook
- 60-second polling for new Hubitat device discovery
- Automatic HA → Hubitat state sync via state_changed listener
- Feedback loop prevention (Hubitat-sourced entities excluded from HA→Hubitat sync)
- `hubitat-ignore` label escape hatch for opt-out
- Graceful error handling with `persistent_notification` alerts
- Retry with exponential backoff on all Hubitat API calls
