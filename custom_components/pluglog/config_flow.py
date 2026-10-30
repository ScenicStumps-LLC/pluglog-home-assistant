"""Adding PlugLog: paste the key made on pluglog.app › Integrations › Home Assistant. It's checked with
PlugLog at once, and the vehicles picked there come with it."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import PlugLogAuthError, PlugLogClient, PlugLogError, PlugLogNotIncluded, looks_like_key
from .const import CONF_URL, DEFAULT_URL, DOMAIN, LOGGER
from .models import Snapshot


class PlugLogConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per PlugLog account (several keys of one account are the same entry)."""

    VERSION = 1

    async def _check(self, key: str, url: str) -> tuple[Snapshot | None, dict[str, str]]:
        """PlugLog's snapshot for [key], or the form's error."""
        if not looks_like_key(key):
            return None, {CONF_API_KEY: "invalid_key_format"}
        try:
            snap = await PlugLogClient(async_get_clientsession(self.hass), key, url).snapshot()
        except PlugLogAuthError:
            return None, {"base": "invalid_auth"}
        except PlugLogNotIncluded:
            return None, {"base": "not_included"}
        except PlugLogError as err:
            LOGGER.debug("PlugLog check failed: %s", err)
            return None, {"base": "cannot_connect"}
        return snap, {}

    def _schema(self, url: str | None) -> vol.Schema:
        fields: dict[Any, Any] = {vol.Required(CONF_API_KEY): str}
        # Another PlugLog (a test server), for advanced users only.
        if self.show_advanced_options:
            fields[vol.Optional(CONF_URL, default=url or DEFAULT_URL)] = str
        return vol.Schema(fields)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            url = user_input.get(CONF_URL, DEFAULT_URL).strip().rstrip("/") or DEFAULT_URL
            snap, errors = await self._check(key, url)
            if snap is not None:
                await self.async_set_unique_id(snap.account or key[-12:])
                self._abort_if_unique_id_configured()
                names = ", ".join(v.name for v in snap.vehicles.values())
                LOGGER.debug("PlugLog key works: %s", names or "no vehicles picked")
                return self.async_create_entry(title="PlugLog", data={CONF_API_KEY: key, CONF_URL: url})
        return self.async_show_form(
            step_id="user", data_schema=self._schema(None), errors=errors, description_placeholders={"page": "pluglog.app › Integrations › Home Assistant"}
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The key was revoked (or is wrong): ask for a new one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            url = entry.data.get(CONF_URL, DEFAULT_URL)
            snap, errors = await self._check(key, url)
            if snap is not None:
                if snap.account and entry.unique_id and snap.account != entry.unique_id:
                    return self.async_abort(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: key})
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}), errors=errors)
