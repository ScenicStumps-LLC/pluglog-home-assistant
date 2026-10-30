"""PlugLog's data in Home Assistant: pushed over one WebSocket, with the REST snapshot at startup and
as the fallback while the connection is down."""

from __future__ import annotations

import asyncio
import random
import time

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PING, PlugLogAuthError, PlugLogClient, PlugLogError, PlugLogNotIncluded, revoked
from .const import DEAD_AFTER, DOMAIN, FALLBACK_INTERVAL, LOGGER, PING_INTERVAL, RECONNECT_MAX, RECONNECT_MIN
from .models import Event, Snapshot, apply, parse_message

type PlugLogConfigEntry = ConfigEntry[PlugLogCoordinator]


class PlugLogCoordinator(DataUpdateCoordinator[Snapshot]):
    """Holds the latest snapshot. The push connection updates it as PlugLog sends; the scheduled
    refresh (every 15 minutes) reads the REST snapshot only while that connection is down."""

    config_entry: PlugLogConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PlugLogConfigEntry, client: PlugLogClient) -> None:
        super().__init__(hass, LOGGER, config_entry=entry, name=DOMAIN, update_interval=FALLBACK_INTERVAL)
        self.client = client
        self.connected = False
        self._stopping = False

    async def _async_update_data(self) -> Snapshot:
        # Connected: PlugLog pushes everything, nothing to ask.
        if self.connected and self.data is not None:
            return self.data
        try:
            return await self.client.snapshot()
        except PlugLogAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PlugLogNotIncluded as err:
            raise UpdateFailed(str(err)) from err
        except PlugLogError as err:
            raise UpdateFailed(str(err)) from err

    # ------------------------------------------------------------------ the push connection

    async def async_listen(self) -> None:
        """Keeps the connection up (a background task for the entry's lifetime), reconnecting with a backoff."""
        delay = RECONNECT_MIN
        while not self._stopping:
            try:
                await self._run_connection()
                delay = RECONNECT_MIN
            except PlugLogAuthError:
                LOGGER.warning("PlugLog no longer accepts this key: add a new one")
                self.connected = False
                self.config_entry.async_start_reauth(self.hass)
                return
            except PlugLogNotIncluded as err:
                LOGGER.warning("%s", err)
                delay = RECONNECT_MAX
            except PlugLogError as err:
                LOGGER.debug("PlugLog connection failed: %s", err)
            finally:
                was = self.connected
                self.connected = False
                if was and not self._stopping:
                    # Down: the snapshot over HTTP says whether PlugLog is still there (entities unavailable if not).
                    self.hass.async_create_task(self.async_refresh())
            if self._stopping:
                return
            await asyncio.sleep(delay + random.uniform(0, delay / 2))
            delay = min(delay * 2, RECONNECT_MAX)

    async def _run_connection(self) -> None:
        ws = await self.client.connect()
        self.connected = True
        LOGGER.debug("Connected to PlugLog")
        last_heard = time.monotonic()
        pinger = self.config_entry.async_create_background_task(self.hass, self._ping(ws), "pluglog ping")
        try:
            while not self._stopping:
                try:
                    msg = await ws.receive(timeout=DEAD_AFTER)
                except TimeoutError:
                    LOGGER.debug("PlugLog went quiet for %s s: connecting again", int(time.monotonic() - last_heard))
                    return
                if msg.type == aiohttp.WSMsgType.TEXT:
                    last_heard = time.monotonic()
                    self._handle(msg.data)
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    if revoked(ws.close_code):
                        raise PlugLogAuthError("The key was revoked on pluglog.app")
                    return
        finally:
            pinger.cancel()
            if not ws.closed:
                await ws.close()

    async def _ping(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            await asyncio.sleep(PING_INTERVAL)
            try:
                await ws.send_str(PING)
            except (aiohttp.ClientError, ConnectionResetError, RuntimeError):
                return

    @callback
    def _handle(self, text: str) -> None:
        message = parse_message(text)
        if message is None:
            return
        if isinstance(message, Event):
            self._fire(message)
            return
        data = apply(self.data, message)
        if data is not None and data is not self.data:
            self.async_set_updated_data(data)

    @callback
    def _fire(self, event: Event) -> None:
        """pluglog_drive_started, …_drive_ended, …_charge_started, …_charge_ended, with the vehicle's device."""
        device = dr.async_get(self.hass).async_get_device(identifiers={(DOMAIN, event.vehicle_id)})
        self.hass.bus.async_fire(event.bus_event, event.bus_data(device.id if device else None))

    async def async_stop(self) -> None:
        self._stopping = True
