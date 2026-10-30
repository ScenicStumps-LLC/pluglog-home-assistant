"""PlugLog's live server, for Home Assistant: the snapshot (REST) and the push connection (WebSocket).

The key goes in the Authorization header only, never in a URL. It's read-only: PlugLog ignores
anything sent on the connection except its text pings.
"""

from __future__ import annotations

import aiohttp

from .const import CLOSE_KEY_REVOKED, SNAPSHOT_PATH, WS_PATH
from .models import Snapshot, looks_like_key, parse_snapshot

__all__ = ["PING", "PlugLogClient", "PlugLogError", "PlugLogAuthError", "PlugLogNotIncluded", "looks_like_key", "revoked"]

PING = '{"type":"ping"}'


class PlugLogError(Exception):
    """PlugLog couldn't be reached, or answered something unexpected."""


class PlugLogAuthError(PlugLogError):
    """The key is wrong or was revoked on pluglog.app."""


class PlugLogNotIncluded(PlugLogError):
    """The account's plan doesn't include Home Assistant (pluglog.app › Integrations › Home Assistant says how)."""


class PlugLogClient:
    """One account's way in, with its key."""

    def __init__(self, session: aiohttp.ClientSession, key: str, url: str) -> None:
        self._session = session
        self._key = key.strip()
        self._url = url.rstrip("/")

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "User-Agent": "HomeAssistant-PlugLog/0.1"}

    def _ws_url(self) -> str:
        if self._url.startswith("https://"):
            return "wss://" + self._url[len("https://") :] + WS_PATH
        if self._url.startswith("http://"):
            return "ws://" + self._url[len("http://") :] + WS_PATH
        return self._url + WS_PATH

    async def snapshot(self) -> Snapshot:
        """The picked vehicles now (Home Assistant's startup, and while the connection is down)."""
        try:
            async with self._session.get(self._url + SNAPSHOT_PATH, headers=self._headers, timeout=aiohttp.ClientTimeout(total=20)) as res:
                await _raise_for(res)
                body = await res.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            raise PlugLogError(f"PlugLog couldn't be reached: {err}") from err
        snap = parse_snapshot(body)
        if snap is None:
            raise PlugLogError("PlugLog answered something unexpected")
        return snap

    async def connect(self) -> aiohttp.ClientWebSocketResponse:
        """The push connection. Raises PlugLogAuthError for a wrong or revoked key."""
        try:
            return await self._session.ws_connect(self._ws_url(), headers=self._headers, timeout=aiohttp.ClientWSTimeout(ws_close=10), autoping=True)
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise PlugLogAuthError("PlugLog didn't accept the key") from err
            if err.status == 403:
                raise PlugLogNotIncluded("Home Assistant isn't included in this PlugLog plan") from err
            raise PlugLogError(f"PlugLog refused the connection ({err.status})") from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise PlugLogError(f"PlugLog couldn't be reached: {err}") from err


async def _raise_for(res: aiohttp.ClientResponse) -> None:
    if res.status == 401:
        raise PlugLogAuthError("PlugLog didn't accept the key")
    if res.status == 403:
        raise PlugLogNotIncluded("Home Assistant isn't included in this PlugLog plan")
    if res.status >= 400:
        raise PlugLogError(f"PlugLog answered {res.status}")


def revoked(close_code: int | None) -> bool:
    """Whether PlugLog closed the connection because its key was revoked."""
    return close_code == CLOSE_KEY_REVOKED
