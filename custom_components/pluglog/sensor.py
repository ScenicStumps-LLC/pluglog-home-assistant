"""PlugLog's sensors, per vehicle: battery, range, charge power, time to full, charge limit, energy
added, speed and when PlugLog last heard the battery."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfPower, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PlugLogConfigEntry, PlugLogCoordinator
from .entity import PlugLogEntity, new_vehicles
from .models import VehicleState

PARALLEL_UPDATES = 0

RANGE_UNITS = {"mi": UnitOfLength.MILES, "km": UnitOfLength.KILOMETERS}
SPEED_UNITS = {"mph": UnitOfSpeed.MILES_PER_HOUR, "km/h": UnitOfSpeed.KILOMETERS_PER_HOUR}


@dataclass(frozen=True, kw_only=True)
class PlugLogSensorDescription(SensorEntityDescription):
    """A sensor: its value from the vehicle's state, and its unit when that's the vehicle's (range, speed)."""

    value: Callable[[VehicleState], float | datetime | None]
    unit: Callable[[VehicleState], str | None] | None = None


SENSORS: tuple[PlugLogSensorDescription, ...] = (
    PlugLogSensorDescription(
        key="battery",
        translation_key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda v: v.battery,
    ),
    PlugLogSensorDescription(
        key="range",
        translation_key="range",
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda v: v.range,
        unit=lambda v: RANGE_UNITS.get(v.range_unit, UnitOfLength.MILES),
    ),
    PlugLogSensorDescription(
        key="charge_power",
        translation_key="charge_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda v: v.charge_power if v.charging else None,
    ),
    PlugLogSensorDescription(
        key="time_to_full",
        translation_key="time_to_full",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value=lambda v: v.time_to_full if v.charging else None,
    ),
    PlugLogSensorDescription(
        key="charge_limit",
        translation_key="charge_limit",
        native_unit_of_measurement=PERCENTAGE,
        value=lambda v: v.charge_limit,
    ),
    PlugLogSensorDescription(
        key="charge_energy_added",
        translation_key="charge_energy_added",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value=lambda v: v.charge_energy_added if v.charging else None,
    ),
    PlugLogSensorDescription(
        key="speed",
        translation_key="speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda v: v.speed if v.driving else None,
        unit=lambda v: SPEED_UNITS.get(v.speed_unit, UnitOfSpeed.MILES_PER_HOUR),
    ),
    PlugLogSensorDescription(
        key="last_updated",
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda v: v.updated_at,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: PlugLogConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        async_add_entities(PlugLogSensor(coordinator, v, d) for v in new_vehicles(coordinator, known) for d in SENSORS)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PlugLogSensor(PlugLogEntity, SensorEntity):
    entity_description: PlugLogSensorDescription

    def __init__(self, coordinator: PlugLogCoordinator, vehicle: VehicleState, description: PlugLogSensorDescription) -> None:
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        v = self.vehicle
        return self.entity_description.value(v) if v else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        v = self.vehicle
        if self.entity_description.unit and v:
            return self.entity_description.unit(v)
        return self.entity_description.native_unit_of_measurement

    @property
    def extra_state_attributes(self) -> dict | None:
        v = self.vehicle
        if self.entity_description.key == "range" and v:
            # From the EPA range × the battery: the car never gave PlugLog a range.
            return {"estimated": v.range_estimated}
        return None
