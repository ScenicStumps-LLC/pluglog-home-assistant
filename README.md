# PlugLog for Home Assistant

Your EVs' battery, range, charging and drives from [PlugLog](https://pluglog.app), as Home Assistant
sensors and events. Pushed live over one connection (no polling), read-only, free.

## What you get

One device per vehicle you pick on pluglog.app (named as in your Garage, so a "Silverado EV" gives
`sensor.silverado_ev_battery`):

| Entity | What it is |
| --- | --- |
| `sensor.<vehicle>_battery` | Battery, % |
| `sensor.<vehicle>_range` | Range, in your PlugLog units (attribute `estimated`: from the EPA range when the car never gave one) |
| `binary_sensor.<vehicle>_charging` | Charging |
| `sensor.<vehicle>_charge_power` | Charging power, kW (while charging) |
| `sensor.<vehicle>_time_to_full` | Minutes to the charge limit (while charging) |
| `sensor.<vehicle>_charge_limit` | Charge limit, %, when the car says |
| `sensor.<vehicle>_energy_added` | kWh added so far (while charging) |
| `binary_sensor.<vehicle>_driving` | Driving |
| `sensor.<vehicle>_speed` | Speed (while driving) |
| `sensor.<vehicle>_last_updated` | When PlugLog last heard the battery, so you can tell how old it is |

Events on Home Assistant's bus, each with `vehicle_id`, `vehicle`, `device_id` and `at`:

- `pluglog_drive_started`: `drive_id`, `started_at`, `battery`
- `pluglog_drive_ended`: `drive_id`, `started_at`, `duration_min`, `distance`, `distance_unit`, `energy_kwh`, `efficiency`, `efficiency_unit`, `battery`
- `pluglog_charge_started`: `charge_id`, `started_at`, `battery`, `charge_limit`
- `pluglog_charge_ended`: `charge_id`, `started_at`, `duration_min`, `energy_added_kwh`, `battery`, `cost` (null for now: PlugLog prices a charge once it's saved)

Entities are unavailable while PlugLog can't be reached, and for a vehicle you untick on pluglog.app.

**Privacy:** the key can't change anything in PlugLog, sees only the vehicles you pick, and never
gets where they are (no location is sent).

## Install

1. **HACS:** HACS › ⋮ › Custom repositories › add this repository's URL, type **Integration**. Then
   find **PlugLog** in HACS, download it, and restart Home Assistant.

   Without HACS: copy `custom_components/pluglog` into your Home Assistant's `config/custom_components/`
   and restart.
2. **Make a key:** on [pluglog.app › Integrations › Home Assistant](https://pluglog.app/integrations/home-assistant)
   (or in the PlugLog phone app: More › Integrations › Home Assistant), tap **Make a key** and copy it
   (it starts with `plk_ha_` and is shown once). Tick the vehicles Home Assistant should see.
3. **Add PlugLog:** Settings › Devices & services › Add integration › **PlugLog**, and paste the key.

Revoking the key on pluglog.app disconnects Home Assistant at once; it then asks for a new key.

## Automation ideas

```yaml
# Porch lights on when a drive ends after dark.
triggers:
  - trigger: event
    event_type: pluglog_drive_ended
    event_data:
      vehicle: Silverado EV
conditions:
  - condition: sun
    after: sunset
actions:
  - action: light.turn_on
    target:
      entity_id: light.porch
```

```yaml
# A phone alert if the truck isn't plugged in by 10 PM with under 50%.
triggers:
  - trigger: time
    at: "22:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.silverado_ev_charging
    state: "off"
  - condition: numeric_state
    entity_id: sensor.silverado_ev_battery
    below: 50
actions:
  - action: notify.mobile_app_my_phone
    data:
      message: "The Silverado isn't charging ({{ states('sensor.silverado_ev_battery') }}%)."
```

## How it works

At startup the integration reads PlugLog's snapshot (`GET https://pluglog.app/v1/live/ha/state`),
then keeps one WebSocket open (`wss://pluglog.app/v1/live/ha`) that PlugLog pushes every change
down, with a text ping every 30 s. If the connection drops it reconnects with a backoff, reading the
snapshot every 15 minutes meanwhile. The key goes in the `Authorization` header only.

## Development

Python 3.13:

```sh
pip install pytest-homeassistant-custom-component ruff
python -m pytest
ruff check . && ruff format --check .
```

## License

MIT (see `LICENSE`).
