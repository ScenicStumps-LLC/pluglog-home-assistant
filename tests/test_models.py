"""Tests of PlugLog's message parsing (custom_components/pluglog/models.py).

models.py imports nothing from Home Assistant, so it's loaded on its own here (the package's
__init__ imports Home Assistant). Run from integrations/home-assistant: python -m pytest
"""

from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
import sys

# models.py on its own (the package's __init__ imports Home Assistant).
_spec = importlib.util.spec_from_file_location("pluglog_models", Path(__file__).parent.parent / "custom_components" / "pluglog" / "models.py")
models = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = models
_spec.loader.exec_module(models)

SILVERADO = {
    "id": "veh-silverado",
    "name": "Silverado EV",
    "make": "Chevrolet",
    "model": "Silverado EV 2WT",
    "year": 2025,
    "battery": 78,
    "range": 303,
    "range_unit": "mi",
    "range_estimated": False,
    "charging": True,
    "charge_power": 11.2,
    "time_to_full": 190,
    "charge_limit": 90,
    "charge_energy_added": 12.35,
    "driving": False,
    "speed": None,
    "speed_unit": "mph",
    "updated_at": "2026-10-29T22:42:00.000Z",
}
SNAPSHOT = {
    "type": "snapshot",
    "account": "0123456789abcdef0123",
    "units": "imperial",
    "vehicles": [SILVERADO, {**SILVERADO, "id": "veh-y", "name": "Model Y"}],
    "at": "2026-10-29T22:42:05.000Z",
}


def test_snapshot_parses_every_vehicle_by_id():
    snap = models.parse_message(json.dumps(SNAPSHOT))
    assert isinstance(snap, models.Snapshot)
    assert snap.account == "0123456789abcdef0123"
    assert snap.units == "imperial"
    assert sorted(snap.vehicles) == ["veh-silverado", "veh-y"]
    v = snap.vehicles["veh-silverado"]
    assert v.name == "Silverado EV"
    assert v.battery == 78.0
    assert v.range == 303.0 and v.range_unit == "mi"
    assert v.charging is True and v.driving is False
    assert v.charge_power == 11.2 and v.time_to_full == 190 and v.charge_limit == 90
    assert v.speed is None
    assert v.updated_at == datetime(2026, 10, 29, 22, 42, tzinfo=UTC)


def test_the_rest_snapshot_is_the_same_shape():
    assert models.parse_snapshot(SNAPSHOT).vehicles["veh-y"].name == "Model Y"
    assert models.parse_snapshot({"type": "state"}) is None
    assert models.parse_snapshot({"type": "snapshot"}) is None
    assert models.parse_snapshot([]) is None


def test_bad_values_become_unknown_not_errors():
    v = models.parse_vehicle(
        {
            "id": "x",
            "battery": "78",
            "range": True,
            "charge_power": float("nan"),
            "range_unit": "furlongs",
            "speed_unit": "knots",
            "charging": "yes",
            "updated_at": "yesterday",
        }
    )
    assert v.battery is None and v.range is None and v.charge_power is None
    assert v.range_unit == "mi" and v.speed_unit == "mph"
    assert v.charging is False
    assert v.updated_at is None
    assert v.name == "PlugLog vehicle"
    assert models.parse_vehicle({"name": "no id"}) is None
    assert models.parse_vehicle("junk") is None


def test_metric_units():
    v = models.parse_vehicle({**SILVERADO, "range": 488, "range_unit": "km", "speed": 100, "speed_unit": "km/h"})
    assert v.range_unit == "km" and v.speed_unit == "km/h" and v.speed == 100


def test_a_state_replaces_only_its_own_vehicle():
    snap = models.parse_snapshot(SNAPSHOT)
    upd = models.parse_message(json.dumps({"type": "state", "vehicle": {**SILVERADO, "charging": False, "battery": 80}, "at": "2026-10-29T22:50:00Z"}))
    assert isinstance(upd, models.StateUpdate)
    after = models.apply(snap, upd)
    assert after.vehicles["veh-silverado"].battery == 80 and after.vehicles["veh-silverado"].charging is False
    assert after.vehicles["veh-y"] is snap.vehicles["veh-y"]
    assert snap.vehicles["veh-silverado"].battery == 78, "the old snapshot is untouched"


def test_a_state_for_a_vehicle_not_in_the_snapshot_is_ignored():
    snap = models.parse_snapshot(SNAPSHOT)
    upd = models.parse_message(json.dumps({"type": "state", "vehicle": {**SILVERADO, "id": "veh-not-picked"}}))
    assert models.apply(snap, upd) is snap
    assert models.apply(None, upd) is None


def test_a_new_snapshot_drops_a_vehicle_no_longer_picked():
    snap = models.parse_snapshot(SNAPSHOT)
    fewer = models.parse_message(json.dumps({**SNAPSHOT, "vehicles": [SILVERADO]}))
    assert list(models.apply(snap, fewer).vehicles) == ["veh-silverado"]


def test_events_become_bus_events_with_flat_data():
    ev = models.parse_message(
        json.dumps(
            {
                "type": "event",
                "event": "drive_ended",
                "vehicle_id": "veh-silverado",
                "vehicle": "Silverado EV",
                "at": "2026-10-29T22:42:00Z",
                "data": {
                    "drive_id": "d1",
                    "distance": 24.9,
                    "distance_unit": "mi",
                    "energy_kwh": 10,
                    "efficiency": 2.49,
                    "efficiency_unit": "mi/kWh",
                    "battery": 70,
                    "nested": {"no": 1},
                    "flag": True,
                },
            }
        )
    )
    assert isinstance(ev, models.Event)
    assert ev.bus_event == "pluglog_drive_ended"
    data = ev.bus_data("device-123")
    assert data["vehicle_id"] == "veh-silverado" and data["vehicle"] == "Silverado EV" and data["device_id"] == "device-123"
    assert data["distance"] == 24.9 and data["efficiency"] == 2.49 and data["battery"] == 70
    assert "nested" not in data and "flag" not in data, "only plain values"
    assert data["at"] == "2026-10-29T22:42:00+00:00"
    assert "device_id" not in ev.bus_data(None)


def test_all_four_events():
    names = {}
    for name in ("drive_started", "drive_ended", "charge_started", "charge_ended"):
        ev = models.parse_message(json.dumps({"type": "event", "event": name, "vehicle_id": "v", "data": {}}))
        names[name] = ev.bus_event
    assert names == {
        "drive_started": "pluglog_drive_started",
        "drive_ended": "pluglog_drive_ended",
        "charge_started": "pluglog_charge_started",
        "charge_ended": "pluglog_charge_ended",
    }
    assert models.parse_message(json.dumps({"type": "event", "event": "lock", "vehicle_id": "v"})) is None
    assert models.parse_message(json.dumps({"type": "event", "event": "drive_ended"})) is None


def test_event_data_never_overrides_the_vehicle():
    ev = models.parse_message(
        json.dumps({"type": "event", "event": "charge_ended", "vehicle_id": "real", "vehicle": "Real", "data": {"vehicle_id": "fake", "energy_added_kwh": 5}})
    )
    assert ev.bus_data()["vehicle_id"] == "real"
    assert ev.bus_data()["energy_added_kwh"] == 5


def test_anything_else_is_ignored():
    for text in ['{"type":"pong"}', "not json", "[]", "null", '{"type":"shares","shares":[]}', '{"type":"state"}']:
        assert models.parse_message(text) is None, text


def test_key_shape():
    assert models.looks_like_key("plk_ha_" + "A" * 43)
    assert models.looks_like_key("  plk_ha_" + "a-_9" * 10 + "  ")
    assert not models.looks_like_key("plk_" + "A" * 43), "the API's read key"
    assert not models.looks_like_key("plk_ha_short")
    assert not models.looks_like_key("plk_ha_" + "A" * 40 + "!!!")
    assert not models.looks_like_key("")
