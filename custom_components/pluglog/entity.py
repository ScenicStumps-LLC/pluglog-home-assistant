"""The base of every PlugLog entity: one device per vehicle, available while PlugLog is reachable."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PlugLogCoordinator
from .models import VehicleState


class PlugLogEntity(CoordinatorEntity[PlugLogCoordinator]):
    """An entity of one vehicle (its device: "Silverado EV", so sensor.silverado_ev_battery)."""

    _attr_has_entity_name = True
    _attr_attribution = "Data from PlugLog"

    def __init__(self, coordinator: PlugLogCoordinator, vehicle: VehicleState, key: str) -> None:
        super().__init__(coordinator)
        self.vehicle_id = vehicle.id
        self._attr_translation_key = key
        self._attr_unique_id = f"{vehicle.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vehicle.id)},
            name=vehicle.name,
            manufacturer=vehicle.make or None,
            model=" ".join(x for x in (str(vehicle.year) if vehicle.year else "", vehicle.model) if x) or None,
            configuration_url="https://pluglog.app/garage",
        )

    @property
    def vehicle(self) -> VehicleState | None:
        """The vehicle now, or None once it's no longer picked on pluglog.app."""
        data = self.coordinator.data
        return data.vehicles.get(self.vehicle_id) if data else None

    @property
    def available(self) -> bool:
        # PlugLog unreachable (the snapshot failed), or the vehicle no longer picked: unavailable.
        return super().available and self.vehicle is not None


def new_vehicles(coordinator: PlugLogCoordinator, known: set[str]) -> list[VehicleState]:
    """The vehicles not given entities yet (picked on pluglog.app since), noted in [known]."""
    data = coordinator.data
    if data is None:
        return []
    fresh = [v for vid, v in data.vehicles.items() if vid not in known]
    known.update(v.id for v in fresh)
    return fresh
