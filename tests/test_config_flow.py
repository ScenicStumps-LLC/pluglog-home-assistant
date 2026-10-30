"""Adding PlugLog: the key is checked with PlugLog; errors say what to do."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pluglog.api import PlugLogAuthError, PlugLogError, PlugLogNotIncluded
from custom_components.pluglog.const import CONF_URL, DEFAULT_URL, DOMAIN

from .conftest import ACCOUNT, KEY


async def test_a_good_key_makes_an_entry_for_the_account(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: f"  {KEY}  "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PlugLog"
    assert result["data"] == {CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL}
    assert result["result"].unique_id == ACCOUNT


async def test_errors(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "plk_notakey"})
    assert result["errors"] == {CONF_API_KEY: "invalid_key_format"}
    mock_snapshot.assert_not_called()

    for error, expected in ((PlugLogAuthError("no"), "invalid_auth"), (PlugLogNotIncluded("no"), "not_included"), (PlugLogError("down"), "cannot_connect")):
        mock_snapshot.side_effect = error
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: KEY})
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": expected}

    # Fixed: it goes through from the same form.
    mock_snapshot.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: KEY})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_one_entry_per_account(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT, data={CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "plk_ha_" + "B" * 43})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_takes_a_new_key_for_the_same_account(hass: HomeAssistant, mock_snapshot: AsyncMock, no_push: AsyncMock) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ACCOUNT, data={CONF_API_KEY: KEY, CONF_URL: DEFAULT_URL})
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    new_key = "plk_ha_" + "C" * 43
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: new_key})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == new_key
