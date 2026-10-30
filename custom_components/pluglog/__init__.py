"""PlugLog for Home Assistant: your EVs' battery, range, charging and drives, pushed live from pluglog.app.

Read-only: it uses a key made on pluglog.app › Integrations › Home Assistant, which can't change
anything, and sees only the vehicles picked there (never where they are).
"""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PlugLogClient
from .const import CONF_URL, DEFAULT_URL
from .coordinator import PlugLogConfigEntry, PlugLogCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PlugLogConfigEntry) -> bool:
    """The snapshot first (not ready until PlugLog answers), then the push connection for as long as the entry lives."""
    client = PlugLogClient(async_get_clientsession(hass), entry.data[CONF_API_KEY], entry.data.get(CONF_URL, DEFAULT_URL))
    coordinator = PlugLogCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, coordinator.async_listen(), "pluglog push connection")
    entry.async_on_unload(coordinator.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlugLogConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
