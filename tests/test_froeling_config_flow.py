"""Test the Froeling integratino config flow."""
from unittest.mock import patch

from homeassistant import config_entries, setup
from custom_components.ha_froeling_euroturbo_40.const import (DOMAIN, CONF_SERIAL_PORT)

async def test_form(hass):
    """Test we get the form."""
    await setup.async_setup_component(hass, "persistent_notification", {})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == None

    with patch(
        "custom_components.ha_froeling_euroturbo_40.async_setup", return_value=True
    ) as mock_setup, patch(
        "custom_components.ha_froeling_euroturbo_40.async_setup_entry",
        return_value=True,
    ) as mock_setup_entry:
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_SERIAL_PORT: "/dev/ttyUSB0",
            },
        )

    assert result2["type"] == "create_entry"
    assert result2["title"] == "ETA Sensor values"
    assert result2["data"][CONF_SERIAL_PORT] ==  "/dev/ttyUSB0"
    
    await hass.async_block_till_done()
    assert len(mock_setup.mock_calls) == 1
    assert len(mock_setup_entry.mock_calls) == 1
