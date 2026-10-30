"""Fixtures: PlugLog's answers, mocked (nothing reaches pluglog.app)."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.pluglog.models import parse_snapshot

pytest_plugins = ["pytest_homeassistant_custom_component"]

KEY = "plk_ha_" + "A" * 43
ACCOUNT = "0123456789abcdef0123"

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


def snapshot_dict(*vehicles: dict) -> dict:
    return {"type": "snapshot", "account": ACCOUNT, "units": "imperial", "vehicles": list(vehicles or [SILVERADO]), "at": "2026-10-29T22:42:05.000Z"}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """custom_components/pluglog is loadable in every test."""


@pytest.fixture
def mock_snapshot() -> Generator[AsyncMock]:
    """PlugLogClient.snapshot answers the Silverado (change return_value / side_effect per test)."""
    with patch("custom_components.pluglog.api.PlugLogClient.snapshot", new_callable=AsyncMock) as m:
        m.return_value = parse_snapshot(snapshot_dict())
        yield m


@pytest.fixture
def no_push() -> Generator[AsyncMock]:
    """The push connection isn't made (the tests feed messages to the coordinator themselves)."""
    with patch("custom_components.pluglog.coordinator.PlugLogCoordinator.async_listen", new_callable=AsyncMock) as m:
        yield m
