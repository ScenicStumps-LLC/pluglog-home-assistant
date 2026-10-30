"""Constants for the PlugLog integration."""

from __future__ import annotations

from datetime import timedelta
import logging

DOMAIN = "pluglog"
LOGGER = logging.getLogger(__package__)

CONF_URL = "url"
DEFAULT_URL = "https://pluglog.app"

# Every PlugLog Home Assistant key starts so (made on pluglog.app › Integrations › Home Assistant).
KEY_PREFIX = "plk_ha_"

# PlugLog's live server, under the site's address.
WS_PATH = "/v1/live/ha"
SNAPSHOT_PATH = "/v1/live/ha/state"

# While the push connection is down, the snapshot is read this often (never while it's up).
FALLBACK_INTERVAL = timedelta(minutes=15)
# A text ping this often (PlugLog answers without waking anything); silence for DEAD_AFTER means the
# connection is gone, and it's made again.
PING_INTERVAL = 30
DEAD_AFTER = 95
# Reconnecting: from RECONNECT_MIN seconds, doubling to RECONNECT_MAX, with some jitter.
RECONNECT_MIN = 2
RECONNECT_MAX = 300

# PlugLog closes a connection whose key was revoked with this code.
CLOSE_KEY_REVOKED = 4001

# The events fired on Home Assistant's bus.
EVENT_DRIVE_STARTED = "pluglog_drive_started"
EVENT_DRIVE_ENDED = "pluglog_drive_ended"
EVENT_CHARGE_STARTED = "pluglog_charge_started"
EVENT_CHARGE_ENDED = "pluglog_charge_ended"
