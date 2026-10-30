"""PlugLog in Home Assistant: a device per vehicle, its entities, pushed updates, events, availability."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.pluglog.api import PlugLogAuthError, PlugLogError
from custom_components.pluglog.const import CONF_URL, DEFAULT_URL, DOMAIN
from custom_components.pluglog.models import parse_snapshot

from .conftest import ACCOUNT, KEY, SILVERADO, snapshot_dict


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT, data={CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_entities_are_named_from_the_vehicle(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    # A US Home Assistant: miles as PlugLog sends them (a metric one converts to km itself).
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    no_push.assert_called_once()

    battery = hass.states.get("sensor.silverado_ev_battery")
    assert battery.state == "78.0"
    assert battery.attributes["unit_of_measurement"] == "%"
    assert battery.attributes["device_class"] == "battery"
    assert hass.states.get("sensor.silverado_ev_range").attributes["unit_of_measurement"] == "mi"
    assert hass.states.get("binary_sensor.silverado_ev_charging").state == STATE_ON
    assert hass.states.get("binary_sensor.silverado_ev_driving").state == STATE_OFF
    assert hass.states.get("sensor.silverado_ev_charge_power").state == "11.2"
    assert hass.states.get("sensor.silverado_ev_time_to_full").state == "190"
    assert hass.states.get("sensor.silverado_ev_charge_limit").state == "90.0"
    assert hass.states.get("sensor.silverado_ev_energy_added").state == "12.35"
    assert hass.states.get("sensor.silverado_ev_speed").state == STATE_UNKNOWN
    assert hass.states.get("sensor.silverado_ev_last_updated").state == "2026-10-29T22:42:00+00:00"

    ent = er.async_get(hass)
    assert ent.async_get("sensor.silverado_ev_battery").unique_id == "veh-silverado_battery"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "veh-silverado")})
    assert device.name == "Silverado EV"
    assert device.manufacturer == "Chevrolet"
    assert device.model == "2025 Silverado EV 2WT"


async def test_pushed_state_and_events(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    entry = await setup(hass)
    coordinator = entry.runtime_data
    # Charging stopped (a state), then the charge's end (an event).
    coordinator._handle(json.dumps({"type": "state", "vehicle": {**SILVERADO, "charging": False, "battery": 81, "charge_power": None}}))
    events = async_capture_events(hass, "pluglog_charge_ended")
    coordinator._handle(
        json.dumps(
            {
                "type": "event",
                "event": "charge_ended",
                "vehicle_id": "veh-silverado",
                "vehicle": "Silverado EV",
                "at": "2026-10-29T23:00:00Z",
                "data": {"energy_added_kwh": 14.2, "cost": None},
            }
        )
    )
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.silverado_ev_charging").state == STATE_OFF
    assert hass.states.get("sensor.silverado_ev_battery").state == "81.0"
    assert hass.states.get("sensor.silverado_ev_charge_power").state == STATE_UNKNOWN
    assert len(events) == 1
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "veh-silverado")})
    assert events[0].data["device_id"] == device.id
    assert events[0].data["energy_added_kwh"] == 14.2
    assert events[0].data["vehicle"] == "Silverado EV"


async def test_a_vehicle_picked_later_gets_entities_and_an_unpicked_one_goes_unavailable(
    hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock
) -> None:
    entry = await setup(hass)
    coordinator = entry.runtime_data
    model_y = {**SILVERADO, "id": "veh-y", "name": "Model Y", "make": "Tesla", "model": "Model Y", "charging": False, "battery": 55}
    coordinator._handle(json.dumps(snapshot_dict(SILVERADO, model_y)))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.model_y_battery").state == "55.0"
    coordinator._handle(json.dumps(snapshot_dict(model_y)))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.silverado_ev_battery").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.model_y_battery").state == "55.0"


async def test_unavailable_when_pluglog_cant_be_reached(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    entry = await setup(hass)
    mock_snapshot.side_effect = PlugLogError("down")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.silverado_ev_battery").state == STATE_UNAVAILABLE
    mock_snapshot.side_effect = None
    mock_snapshot.return_value = parse_snapshot(snapshot_dict())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.silverado_ev_battery").state == "78.0"


async def test_not_ready_until_pluglog_answers(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    mock_snapshot.side_effect = PlugLogError("down")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT, data={CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_a_revoked_key_asks_for_a_new_one(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    mock_snapshot.side_effect = PlugLogAuthError("revoked")
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT, data={CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_unload(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    entry = await setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
