"""PlugLog's messages, parsed: pure Python (no Home Assistant imports), so it's tested on its own.

PlugLog sends (see pluglog/src/lib/home-assistant-rules.ts in PlugLog's repository):

* ``{"type": "snapshot", "account", "units", "vehicles": [<state>…], "at"}``: first on every
  connection, again when the vehicles picked on pluglog.app change, and as the REST snapshot.
* ``{"type": "state", "vehicle": <state>, "at"}``: one vehicle changed (at most every few seconds
  while it drives or charges).
* ``{"type": "event", "event", "vehicle_id", "vehicle", "at", "data": {…}}``: a drive or charge
  started or ended.

Anything else (a ``pong``, a type from a newer PlugLog) is ignored.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
import json
from typing import Any

# PlugLog's event names → the events fired on Home Assistant's bus.
BUS_EVENTS = {
    "drive_started": "pluglog_drive_started",
    "drive_ended": "pluglog_drive_ended",
    "charge_started": "pluglog_charge_started",
    "charge_ended": "pluglog_charge_ended",
}

KEY_PREFIX = "plk_ha_"
_KEY_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")

RANGE_UNITS = ("mi", "km")
SPEED_UNITS = ("mph", "km/h")


@dataclass(frozen=True)
class VehicleState:
    """One vehicle as PlugLog last said. None: no value now (charge power while parked)."""

    id: str
    name: str
    make: str = ""
    model: str = ""
    year: int | None = None
    battery: float | None = None
    range: float | None = None
    range_unit: str = "mi"
    range_estimated: bool = False
    charging: bool = False
    charge_power: float | None = None
    time_to_full: int | None = None
    charge_limit: float | None = None
    charge_energy_added: float | None = None
    driving: bool = False
    speed: float | None = None
    speed_unit: str = "mph"
    updated_at: datetime | None = None


@dataclass(frozen=True)
class Snapshot:
    """Everything PlugLog lets Home Assistant see: the account's units and its picked vehicles."""

    account: str
    units: str
    vehicles: dict = field(default_factory=dict)  # vehicle id → VehicleState
    at: datetime | None = None


@dataclass(frozen=True)
class StateUpdate:
    vehicle: VehicleState
    at: datetime | None = None


@dataclass(frozen=True)
class Event:
    """A drive or charge that started or ended; [bus_event] is what Home Assistant fires."""

    event: str
    vehicle_id: str
    vehicle: str
    at: datetime | None
    data: dict

    @property
    def bus_event(self) -> str:
        return BUS_EVENTS[self.event]

    def bus_data(self, device_id: str | None = None) -> dict:
        """The bus event's data: the vehicle, when, and the event's own figures, flat for templates."""
        out = {"vehicle_id": self.vehicle_id, "vehicle": self.vehicle, "at": self.at.isoformat() if self.at else None}
        if device_id:
            out["device_id"] = device_id
        for key, value in self.data.items():
            if key not in out:
                out[key] = value
        return out


Message = Snapshot | StateUpdate | Event


def looks_like_key(key: str) -> bool:
    """Whether [key] has a PlugLog Home Assistant key's shape: plk_ha_ and 32 to 64 URL-safe
    characters (PlugLog checks it again)."""
    key = key.strip() if isinstance(key, str) else ""
    rest = key[len(KEY_PREFIX) :]
    return key.startswith(KEY_PREFIX) and 32 <= len(rest) <= 64 and set(rest) <= _KEY_CHARS


def _number(value: Any) -> float | None:
    """A finite number (never a bool), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return float(value)


def _int(value: Any) -> int | None:
    n = _number(value)
    return int(n) if n is not None else None


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def parse_time(value: Any) -> datetime | None:
    """An ISO 8601 time ("2026-10-29T22:42:00.000Z") as an aware datetime, else None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_vehicle(raw: Any) -> VehicleState | None:
    """One vehicle's state, or None when it has no id."""
    if not isinstance(raw, Mapping):
        return None
    vid = raw.get("id")
    if not isinstance(vid, str) or not vid:
        return None
    range_unit = raw.get("range_unit")
    speed_unit = raw.get("speed_unit")
    return VehicleState(
        id=vid,
        name=_text(raw.get("name")) or "PlugLog vehicle",
        make=_text(raw.get("make")),
        model=_text(raw.get("model")),
        year=_int(raw.get("year")),
        battery=_number(raw.get("battery")),
        range=_number(raw.get("range")),
        range_unit=range_unit if range_unit in RANGE_UNITS else "mi",
        range_estimated=raw.get("range_estimated") is True,
        charging=raw.get("charging") is True,
        charge_power=_number(raw.get("charge_power")),
        time_to_full=_int(raw.get("time_to_full")),
        charge_limit=_number(raw.get("charge_limit")),
        charge_energy_added=_number(raw.get("charge_energy_added")),
        driving=raw.get("driving") is True,
        speed=_number(raw.get("speed")),
        speed_unit=speed_unit if speed_unit in SPEED_UNITS else "mph",
        updated_at=parse_time(raw.get("updated_at")),
    )


def parse_snapshot(raw: Any) -> Snapshot | None:
    """The snapshot (a message or the REST answer), or None."""
    if not isinstance(raw, Mapping) or raw.get("type") != "snapshot" or not isinstance(raw.get("vehicles"), list):
        return None
    vehicles = {}
    for item in raw["vehicles"]:
        v = parse_vehicle(item)
        if v is not None:
            vehicles[v.id] = v
    units = raw.get("units")
    return Snapshot(
        account=_text(raw.get("account")), units=units if units in ("imperial", "metric") else "imperial", vehicles=vehicles, at=parse_time(raw.get("at"))
    )


def parse_message(text: str) -> Message | None:
    """One message from PlugLog, or None for anything it doesn't know (a pong, junk, a newer type)."""
    try:
        raw = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(raw, Mapping):
        return None
    kind = raw.get("type")
    if kind == "snapshot":
        return parse_snapshot(raw)
    if kind == "state":
        v = parse_vehicle(raw.get("vehicle"))
        return StateUpdate(vehicle=v, at=parse_time(raw.get("at"))) if v else None
    if kind == "event":
        name = raw.get("event")
        vid = raw.get("vehicle_id")
        if name not in BUS_EVENTS or not isinstance(vid, str) or not vid:
            return None
        data = raw.get("data")
        clean = {}
        if isinstance(data, Mapping):
            for key, value in data.items():
                if isinstance(key, str) and (value is None or isinstance(value, (str, int, float)) and not isinstance(value, bool)):
                    clean[key] = value
        return Event(event=name, vehicle_id=vid, vehicle=_text(raw.get("vehicle")), at=parse_time(raw.get("at")), data=clean)
    return None


def apply(current: Snapshot | None, message: Message) -> Snapshot | None:
    """The snapshot after [message]: a snapshot replaces it (a vehicle no longer picked drops out);
    a state replaces that vehicle's, only for a vehicle in it (PlugLog never sends others); an event
    leaves it as it is."""
    if isinstance(message, Snapshot):
        return message
    if isinstance(message, StateUpdate):
        if current is None or message.vehicle.id not in current.vehicles:
            return current
        vehicles = dict(current.vehicles)
        vehicles[message.vehicle.id] = message.vehicle
        return replace(current, vehicles=vehicles, at=message.at or current.at)
    return current
