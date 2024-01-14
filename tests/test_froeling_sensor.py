"""Test sensor for froeling heater integration."""
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.ha_froeling_euroturbo_40.const import (DOMAIN, CONF_CAN_BUS,)
from custom_components.ha_froeling_euroturbo_40.sensor import FrlngButtonCodes
import asyncio
import can

def send_can_string(test_can, line, text):
    display_offsets = [0x80,0xc0,0x94,0xd4]
    assert 0<= line <= 3
    msg = can.Message(arbitration_id=0x021, is_extended_id=False, data=[0x00,display_offsets[line]])
    test_can.send(msg)
    for char in text:
        encoded = bytes(char,"utf-8")
        if len(encoded)>1:
            if char == '°':
                encoded = b'\xdf'
            elif char == 'ß':
                encoded = b'\xe2'
            elif char == 'ä':
                encoded = b'\xe1'
            elif char == 'ü':
                encoded = b'\xf5'
        assert len(encoded) == 1
        msg = can.Message(arbitration_id=0x021, is_extended_id=False, data=encoded)
        assert msg.dlc == 1
        test_can.send(msg)
    # set address to next line, this will triggers the implementation to parse the last selected display line
    if line == 3:
        line = 0
    else:
        line += 1
    msg = can.Message(arbitration_id=0x021, is_extended_id=False, data=[0x00,display_offsets[line]])
    test_can.send(msg)

async def test_sensor(hass):
    """Test sensor."""
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_CAN_BUS: "unittesting"
        })
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    test_can = can.interface.Bus('test_can', interface='virtual')
    reader = can.AsyncBufferedReader()
    notifier = can.Notifier(test_can, [reader], loop=hass.loop)

    await asyncio.sleep(0.1)
    # wait for first button 
    cnt = 0
    while cnt < 3:
        msg = await reader.get_message()
        if msg.data[0] == FrlngButtonCodes.BUTTON_LEFT:
            cnt += 1
    send_can_string(test_can,0,"Kessel in Betrieb   ")
    send_can_string(test_can,1,"Pufferladezust. 80% ")
    send_can_string(test_can,2,"Gebläse IST   1500U ")
    send_can_string(test_can,3,"Außentemperatur -1° ")
    msg = await reader.get_message()
    while msg.data[0] != FrlngButtonCodes.BUTTON_RIGHT:
        msg = await reader.get_message()
    state = hass.states.get("sensor.froling_euroturbo40_froeling1_pufferladezust")
    assert state
    assert state.state == "80"
    state = hass.states.get("sensor.froling_euroturbo40_froeling1_geblase_ist")
    assert state
    assert state.state == "1500"
    state = hass.states.get("sensor.froling_euroturbo40_froeling1_aussentemperatur")
    assert state
    assert state.state == "-1"

    # wait for first right button
    msg = await reader.get_message()
    while msg.data[0] != FrlngButtonCodes.BUTTON_LEFT:
        msg = await reader.get_message()
    
    send_can_string(test_can,0,"Puffertmp. oben 82° ")
    send_can_string(test_can,1,"Puffertmp.mitte 72° ")
    send_can_string(test_can,2,"Puffertmp.unten 62° ")
    send_can_string(test_can,3,"                    ")
        
    msg = await reader.get_message()
    while msg.data[0] != FrlngButtonCodes.BUTTON_RIGHT:
        msg = await reader.get_message()

    state = hass.states.get("sensor.froling_euroturbo40_froeling1_puffertmp_oben") 
    assert state
    assert state.state == "82"
    state = hass.states.get("sensor.froling_euroturbo40_froeling1_puffertmp_mitte")
    assert state
    assert state.state == "72"
    state = hass.states.get("sensor.froling_euroturbo40_froeling1_puffertmp_unten")
    assert state
    assert state.state == "62"
    
    msg = await reader.get_message()
    while msg.data[0] != FrlngButtonCodes.BUTTON_RIGHT:
        msg = await reader.get_message()

    send_can_string(test_can,0,"Kesseltür ist offen ")
    send_can_string(test_can,1,"                    ")
    send_can_string(test_can,2,"                    ")
    send_can_string(test_can,3,"                    ")
    await asyncio.sleep(0.5)
   

    msg = await reader.get_message()
    while msg.data[0] != FrlngButtonCodes.BUTTON_RIGHT:
        msg = await reader.get_message()

    state = hass.states.get("sensor.froling_euroturbo40_froeling1_kessel_status")
    assert state
    assert state.state == "Kesseltür ist offen"
        
    reader.stop()
    notifier.stop()
    test_can.shutdown()
    await hass.config_entries.async_remove(entry.entry_id)
