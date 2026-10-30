"""PlugLog's binary sensors, per vehicle: charging and driving."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PlugLogConfigEntry, PlugLogCoordinator
from .entity import PlugLogEntity, new_vehicles
from .models import VehicleState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PlugLogBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[VehicleState], bool]


BINARY_SENSORS: tuple[PlugLogBinaryDescription, ...] = (
    PlugLogBinaryDescription(key="charging", translation_key="charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING, value=lambda v: v.charging),
    PlugLogBinaryDescription(key="driving", translation_key="driving", device_class=BinarySensorDeviceClass.MOVING, value=lambda v: v.driving),
)


async def async_setup_entry(hass: HomeAssistant, entry: PlugLogConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def add_new() -> None:
        async_add_entities(PlugLogBinarySensor(coordinator, v, d) for v in new_vehicles(coordinator, known) for d in BINARY_SENSORS)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PlugLogBinarySensor(PlugLogEntity, BinarySensorEntity):
    entity_description: PlugLogBinaryDescription

    def __init__(self, coordinator: PlugLogCoordinator, vehicle: VehicleState, description: PlugLogBinaryDescription) -> None:
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        v = self.vehicle
        return self.entity_description.value(v) if v else None
