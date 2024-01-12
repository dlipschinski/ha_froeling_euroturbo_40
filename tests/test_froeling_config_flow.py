"""Test Fröling config flow."""

import pytest

from custom_components.ha_froeling_euroturbo_40.const import CONF_CAN_BUS, DEFAULT_TITLE, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

VALID_CONFIG = {CONF_CAN_BUS: "can0"}
VALID_LEGACY_CONFIG = {CONF_NAME: "Fröling", CONF_CAN_BUS: "can0"}

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_show_form(hass: HomeAssistant) -> None:
    """Test that the form is served with no input."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        VALID_CONFIG,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_TITLE
    assert result["data"][CONF_CAN_BUS] == VALID_CONFIG[CONF_CAN_BUS]
