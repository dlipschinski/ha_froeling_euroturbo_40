"""Platform for sensor integration."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    REVOLUTIONS_PER_MINUTE,
    PERCENTAGE,
    EVENT_HOMEASSISTANT_STOP,
)

from collections.abc import Mapping
import can
from can.notifier import MessageRecipient
import re
import enum
from typing import (List,Any)
import binascii
import threading
import asyncio
from .const import (
    LOGGER,
    DEFAULT_DEVICE_NAME,
    CONF_CAN_BUS,
    SIGNAL_FRLNG_TELEGRAM,
    DOMAIN
)


from enum import StrEnum

SENSOR_UNIT_MAPPING = {
    "U": REVOLUTIONS_PER_MINUTE,
    "°": UnitOfTemperature.CELSIUS,
    "%": PERCENTAGE,
    "None": None
}
   

class FrlngCANArbID(enum.IntEnum):
    CMD_TIME = 0x018
    CMD_DISPLAY = 0x021
    CMD_BUTTON = 0x02f
    # 0x0c0, 0x040 and 0x022 are note used, seems to be used from main to addon board

class FrlngButtonCodes(enum.IntEnum):
    BUTTON_LEFT   = 0x02
    BUTTON_DOWN   = 0x04
    BUTTON_RIGHT  = 0x08
    BUTTON_CHANGE = 0x10
    BUTTON_BURNUP = 0x20
    BUTTON_INFO   = 0x40
    BUTTON_ON_OFF = 0x80
    BUTTON_NO_BUT = 0x00

lcd_line_addr = [0x80,0xc0,0x94,0xd4]

update_send_seq = [
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT, # now we are in the main menu (when we have been in a submenu or a error was there)
            # cursor is now on "pufferladezust."
            FrlngButtonCodes.BUTTON_RIGHT, # "puffertemps"
            FrlngButtonCodes.BUTTON_LEFT,  # back on pufferladezust.
            FrlngButtonCodes.BUTTON_DOWN,  # kesselrücklauf
            FrlngButtonCodes.BUTTON_DOWN,  # Heizungspumpe1
            FrlngButtonCodes.BUTTON_DOWN,  # Heizungspumpe2
            FrlngButtonCodes.BUTTON_RIGHT, # Vorlauftemp
            FrlngButtonCodes.BUTTON_LEFT,  # Heizungspumpe2
            FrlngButtonCodes.BUTTON_DOWN,  # Außentemperatur
            FrlngButtonCodes.BUTTON_DOWN,  # Außentemperatur
            FrlngButtonCodes.BUTTON_DOWN,  # Gebläse
            FrlngButtonCodes.BUTTON_RIGHT, # Gebläse soll/ist
            FrlngButtonCodes.BUTTON_LEFT,  # Gebläse
            FrlngButtonCodes.BUTTON_DOWN,  # Stellmotor oben
            FrlngButtonCodes.BUTTON_RIGHT, # Stellmotor oben details
            FrlngButtonCodes.BUTTON_LEFT,  # Stellmotor oben
            FrlngButtonCodes.BUTTON_DOWN,  # Stellmotor unten
            FrlngButtonCodes.BUTTON_RIGHT, # Stellmotor unten details
            FrlngButtonCodes.BUTTON_LEFT,  # Stellmotor unten
            FrlngButtonCodes.BUTTON_DOWN,  # Sauerstoffwert
            FrlngButtonCodes.BUTTON_LEFT,  # Pufferladezustand
            FrlngButtonCodes.BUTTON_LEFT,  # Pufferladezustand
]

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""

    canbus=config_entry.data.get(CONF_CAN_BUS)
    LOGGER.debug("Opening " + str(canbus))
    hass.data[DOMAIN] = FrlngCANCom( hass, config_entry.data, async_add_entities)
    await hass.data[DOMAIN].can_start_update()

async def async_remove_entry(hass, config_entry):
    hass.data[DOMAIN].can_stop_update()

class FrlngCANCom():
    """Handle the can communication."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: Mapping[str, Any],
        async_add_entities: AddEntitiesCallback
    ):
        """Initialize the Serial connection."""
        self._hass = hass
        self._async_add_entities = async_add_entities
        self._can_net_dev = config[CONF_CAN_BUS]
        self._dev_id =  "Froeling1" #config[CONF_DEVICE_NAME] todo get this from config flow
        self._lcd_buf = [0 for i in range(500)] # 0xd4+20 would be big enough
        self._lcd_offs = None
        self._lcd_addr = None
        self._last_line = 0
        self._registered_values = dict()
        try:
            self._can = self.init_can(self._can_net_dev)
            self._can_listeners: List[MessageRecipient] = [self.can_msg_receive,]
        except Exception as error:
            LOGGER.error("Failed to init: " + str(self._can_net_dev) + " Error:" + str(error))
    
    def init_can(self, can_net_dev):
        """ Init the CAN bus """
        if can_net_dev == "unittesting":
            return can.Bus('test_can', interface='virtual')
        return can.Bus(interface='socketcan', channel=can_net_dev, receive_own_messages=False)

    async def can_start_update(self):
        """Start receiving"""
        LOGGER.info("Starting CAN bus")
        try:
            self._notifier = can.Notifier(self._can, self._can_listeners, loop=self._hass.loop)
        except Exception as error:
            LOGGER.error("Failed to init can bus notifier. Error:" + str(error) + str(type(self._hass)))
        #else:
            #while True:
            #    await asyncio.sleep(0.5)
                # todo send display udpate sequence

    async def can_stop_update(self):
        """Stop receiving"""
        LOGGER.info("Stopping CAN bus")
        self._notifier.stop()

    def can_msg_receive(self, msg: can.Message) -> None:
        """Callback on new CAN message"""
        if msg.arbitration_id == FrlngCANArbID.CMD_DISPLAY:
            self.handle_display_data(msg)
        elif msg.arbitration_id == FrlngCANArbID.CMD_BUTTON:
            self.handle_button_data(msg)
        elif msg.arbitration_id == FrlngCANArbID.CMD_TIME:
            self.handle_time_data(msg)

    def handle_display_data(self, msg):
        """Callback for display messages"""
        if msg.dlc == 1:
            # 1 byte message: display char
            if self._lcd_addr == None or self._lcd_offs == None:
                LOGGER.debug("LCD offset or address not set")
                return
            try:
                self._lcd_buf[self._lcd_addr + self._lcd_offs] = self.conv_lcd_chars(msg.data[0])
            except:
                LOGGER.error("Could not write to resulting display address:" + str(self._lcd_addr) + " Offset:" + str(self._lcd_offs))
                assert False
            self._lcd_offs += 1
        elif msg.dlc == 2:
            # 2 byte message: display address
            try:
                self._lcd_offs = 0
                self._lcd_addr = int.from_bytes(bytearray([msg.data[0],msg.data[1]]))
                # lets check if the new address is a new line, if yes parse the last line
                
                cur_line = 0
                for addr in lcd_line_addr:
                    if addr <= self._lcd_addr < (addr+20):
                        break
                    cur_line += 1
                if self._last_line != cur_line:
                    self.parse_lcd(self._last_line)
                    self._last_line = cur_line
            except Exception as error:
                LOGGER.warning("Fail to set display address: " +  str(error))
                self._lcd_addr = 0x80
        else:
            LOGGER.warning("Wrong display message length: " + str(msg.dlc))

    def parse_lcd(self, cur_line):
        """"Try to find name, value unit pairs in current display line"""
        try:
            # get the current lcd line and create string of it
            cur_lcd_line = ''.join(self._lcd_buf[lcd_line_addr[cur_line]:lcd_line_addr[cur_line]+20])
        except:
            LOGGER.error("Fail to join lcd line: " + str(error) + " Current-LCDline:" + str(cur_line) +  " Address: " + str(self._lcd_addr))
            return
        try:
            splitted = re.split(r'([-]?\d+[.\d]*)', cur_lcd_line)
            name = splitted[0].strip()
            value = splitted[1].strip()
            unit = splitted[2].strip()
            LOGGER.info("Name: " + str(name) + " Value: " + str(value) + " Unit: " + str(unit) + " LCD Line: " + cur_lcd_line)
        # create or update the sensor
        except Exception as error:
            # could happen for generic display text without a value

            if cur_lcd_line.find("Kessel") == 0:
                name = "kessel_status"
                value = cur_lcd_line
                unit = "None"
            else:
                LOGGER.error("Exception during parsing lcd line: " + str(error) + " Current-LCDline:" + cur_lcd_line)
                return
        try:
            sensor_entry = self._registered_values[name+unit]
        except:
            # instantiate the sensor
            LOGGER.info("Adding sensor: Name: " + str(name) + " Value: " + str(value) + " Unit: " + str(unit))
            frlng_sens = FrlngEntity(self._dev_id, name, unit, value)
            self._registered_values[name+unit] = frlng_sens
            self._async_add_entities([frlng_sens], update_before_add=True)
        else:
            # update the sensor
            LOGGER.debug("Update sensor: Name: " + str(name) + " Value: " + str(value) + " Unit: " + str(unit))
            async_dispatcher_send(
                self._hass, SIGNAL_FRLNG_TELEGRAM+sensor_entry.get_unique_id(), name, value, unit
            )

    def conv_lcd_chars(self, char):
        """Convert special lcd characters codes"""
        if char == 0xdf:
            return "°"
        if char == 0xe1:
            return "ä"
        if char == 0xe2:
            return "ß"
        if char == 0xf5:
            return "ü"
        # todo ÄÖÜö
        return chr(char)

    def handle_button_data(self, msg):
        """Callback for button messages"""
        # todo: lock polling mode for ~10min
        return

    def handle_time_data(self, msg):
        """Callback for time messages"""
        return

class FrlngEntity(SensorEntity):
    """Entity reading values from fröling can lcd display message."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, dev_id, name, unit, value):
        """Initialize a Fröling Entity."""
        self._dev_id = dev_id
        self._name = name
        self._unit = unit
        self._value = value
        self._async_remove_dispatcher = None
        self._attr_unique_id = f"{dev_id}_{name}"
        #self._attr_device_info = DeviceInfo(
        #    identifiers={(DOMAIN, self._dev_id)},
        #    name=DEFAULT_DEVICE_NAME,
        #)
    def get_unique_id(self):
        return self._attr_unique_id
    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        def handle_new_value(name, value, unit):
            """Update value and update stat if changed"""
            assert self._name == name
            assert self._unit == unit
            if self._value == value:
                return
            self._value = value
            self.async_write_ha_state()

        self._async_remove_dispatcher = async_dispatcher_connect(
            self.hass, SIGNAL_FRLNG_TELEGRAM+self._attr_unique_id, handle_new_value
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._async_remove_dispatcher:
            self._async_remove_dispatcher()

    @property
    def native_value(self) -> str:
        """Return the value of the last received telegram."""
        return self._value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return SENSOR_UNIT_MAPPING[self._unit]