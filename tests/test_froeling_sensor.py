"""Test sensor for froeling heater integration."""
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.ha_froeling_euroturbo_40.const import (DOMAIN, CONF_SERIAL_PORT,)
import asyncio
import serial

async def test_sensor(hass):
    """Test sensor. This requires a loopback (tx->rx) connection on the /dev/ttyUSB0"""
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_SERIAL_PORT: "/dev/ttyUSB0"
        })
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ser = serial.Serial("/dev/ttyUSB0",19200)
    
    # set kessel temp to 42.2 and check response
    ser.write(bytes([123, 77, 68, 5, 183, 0x08, 0x00, 0x08, 0x01, 0xa6, 125]))
    await asyncio.sleep(0.1)
    state = hass.states.get("sensor.kessel_temperatur")
    assert state
    assert state.state == "42.2"

    # set kessel temp to 42.3 and check response
    ser.write(bytes([123, 77, 68, 5, 184, 0x08, 0x00, 0x08, 0x01, 0xa7, 125]))
    await asyncio.sleep(0.1)
    state = hass.states.get("sensor.kessel_temperatur")
    assert state
    assert state.state == "42.3"
