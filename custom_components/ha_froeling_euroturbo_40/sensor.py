"""Platform for sensor integration."""
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.util.dt import utcnow
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    REVOLUTIONS_PER_MINUTE,
    PERCENTAGE,
    EntityCategory,
    EVENT_HOMEASSISTANT_STOP,
)

from collections.abc import Mapping
import can
from can.notifier import MessageRecipient
import re
import enum
from typing import (List,Any)
import binascii
import asyncio
import time
import slugify 
from datetime import timedelta

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
    "None": None,
    "h" : UnitOfTime.HOURS
}

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="abgastemp_ist",
        translation_key="abgas_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="abgastemp_soll",
        translation_key="abgas_soll_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="aussentemperatur",
        translation_key="ausen_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="puffertmp_oben",
        translation_key="puffer_temperatur_oben",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="puffertmp_mitte",
        translation_key="puffer_temperatur_mitte",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="puffertmp_unten",
        translation_key="puffer_temperatur_unten",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="kesselrucklauft",
        translation_key="kessel_rucklauf_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="kesseltemp_ist",
        translation_key="kessel_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="kesseltempsoll",
        translation_key="kessel_soll_temperatur",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="pufferladezust",
        icon="mdi:water-boiler",
        translation_key="puffer_ladezustand",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="betriebsstd",
        translation_key="betriebsstunden",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
    ),
    SensorEntityDescription(
        key="geblase_ist",
        translation_key="geblase_drehzahl",
        icon="mdi:fan",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
    ),
    SensorEntityDescription(
        key="stellmot_u_ist",
        translation_key="stellmotor_unten",
        icon="mdi:arrow-oscillating",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="stellmot_o_ist",
        translation_key="stellmotor_oben",
        icon="mdi:arrow-oscillating",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="sauerstoffwert",
        translation_key="sauerstoffwert",
        icon="mdi:engine-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SensorEntityDescription(
        key="kessel_status",
        translation_key="kessel_status",
        icon="mdi:list-status",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="heizungspumpe1",
        translation_key="heizungspumpe1",
        icon="mdi:pump",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="heizungspumpe2",
        translation_key="heizungspumpe2",
        icon="mdi:pump",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="rucklaufmischer",
        translation_key="ruecklaufmischer",
        icon="mdi:pump",
        device_class=SensorDeviceClass.ENUM,
    ),
    SensorEntityDescription(
        key="vorlauftmp2_ist",
        translation_key="vorlauf_ist_temperatur_2",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="vorlauftmp2soll",
        translation_key="vorlauf_soll_temperatur_2",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),

)

SENSORS = {desc.key: desc for desc in SENSOR_TYPES}

class FrlngCANArbID(enum.IntEnum):
    CMD_TIME = 0x018
    CMD_DISPLAY = 0x021
    CMD_BUTTON = 0x02f
    # 0x0c0, 0x040 and 0x022 are note used, seems to be used from main to addon board

class FrlngButtonCodes(enum.IntEnum):
    BUTTON_UP     = 0x01
    BUTTON_LEFT   = 0x02
    BUTTON_DOWN   = 0x04
    BUTTON_RIGHT  = 0x08
    BUTTON_CHANGE = 0x10
    BUTTON_BURNUP = 0x20
    BUTTON_INFO   = 0x40
    BUTTON_ON_OFF = 0x80
    BUTTON_NO_BUT = 0x00
    REFRESH_DISPLAY = 0xff

lcd_line_addr = [0x80,0xc0,0x94,0xd4]

update_send_seq = [
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT, # now we are in the main menu (when we have been in a submenu or a error was there)
            # cursor is now on "pufferladezust."
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_UP,
            FrlngButtonCodes.BUTTON_RIGHT, # "abgastemps"
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_UP,
            FrlngButtonCodes.BUTTON_RIGHT, # "kesseltemps"
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,
            FrlngButtonCodes.BUTTON_LEFT, # back to main menu
            FrlngButtonCodes.BUTTON_RIGHT, # "puffertemps"
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # back on pufferladezust.
            FrlngButtonCodes.BUTTON_DOWN,  # kesselrücklauf
            FrlngButtonCodes.BUTTON_RIGHT, # Kesselrücklauf details
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # kesselrücklauf
            FrlngButtonCodes.BUTTON_DOWN,  # Heizungspumpe1
            FrlngButtonCodes.BUTTON_DOWN,  # Heizungspumpe2
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_RIGHT, # Vorlauftemp
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Heizungspumpe2
            FrlngButtonCodes.BUTTON_DOWN,  # Außentemperatur
            FrlngButtonCodes.BUTTON_DOWN,  # Gebläse
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_RIGHT, # Gebläse soll/ist
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Gebläse
            FrlngButtonCodes.BUTTON_DOWN,  # Stellmotor oben
            FrlngButtonCodes.BUTTON_RIGHT, # Stellmotor oben details
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Stellmotor oben
            FrlngButtonCodes.BUTTON_DOWN,  # Stellmotor unten
            FrlngButtonCodes.BUTTON_RIGHT, # Stellmotor unten details
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Stellmotor unten
            FrlngButtonCodes.BUTTON_DOWN,  # Sauerstoffwert
            FrlngButtonCodes.BUTTON_RIGHT,  # Sauerstoffwert details
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Sauerstoffwert
            FrlngButtonCodes.REFRESH_DISPLAY,
            FrlngButtonCodes.BUTTON_LEFT,  # Pufferladezustand
            FrlngButtonCodes.BUTTON_LEFT,  # Pufferladezustand
            FrlngButtonCodes.BUTTON_LEFT,  # Pufferladezustand
]

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up entry."""

    canbus=config_entry.data.get(CONF_CAN_BUS)
    LOGGER.debug("Opening " + str(canbus))
    hass.data[DOMAIN] = FrlngCANCom( hass, config_entry.data, async_add_entities)
    def _init_can():
        hass.data[DOMAIN].init_can()
    await hass.async_add_executor_job(_init_can)

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
        self._lcd_buf = [' ' for i in range(500)] # 0xd4+20 would be big enough
        self._lcd_offs = None
        self._lcd_addr = None
        self._last_line = 0
        self._registered_values = dict()
        self._pause_buttonsseq = False

    def init_can(self):
        """ Init the CAN bus """
        try:
            if self._can_net_dev == "unittesting":
                self._can = can.Bus('test_can', interface='virtual')
            self._can = can.Bus(interface='socketcan', channel=self._can_net_dev, receive_own_messages=False)
            self._can_listeners: List[MessageRecipient] = [self.can_msg_receive,]
        except Exception as error:
            LOGGER.error("Failed to init: " + str(self._can_net_dev) + " Error:" + str(error))

    async def send_button(self,button):
        msg = can.Message(arbitration_id=FrlngCANArbID.CMD_BUTTON,is_extended_id=False,data=[button])
        self._can.send(msg)
        await asyncio.sleep(0.15)
        msg.data[0] = FrlngButtonCodes.BUTTON_NO_BUT
        self._can.send(msg)
        await asyncio.sleep(0.25)

    async def send_loop(self):
        """ The send loop thread """
        LOGGER.debug("Entering CAN send loop")
        min_time = timedelta(seconds=60)
        last_update_time = utcnow()-min_time # set update time to directly start updating the display
        while self._send_running:
            now = utcnow()
            if now - last_update_time > min_time:
                for curr_send_seq in update_send_seq:
                    if self._send_running == False:
                        return
                    if curr_send_seq == FrlngButtonCodes.REFRESH_DISPLAY:
                        await asyncio.sleep(0.75)
                        self.parse_lcd()
                    else:
                        if self._pause_buttonsseq == True:
                            # block updating for 10minutes
                            LOGGER.info("User pressed button, stopping refresh for 10 minutes")
                            self._pause_buttonsseq = False
                            await asyncio.sleep(10*60)                           
                            # start the sequence from beginnign
                            break
                        await self.send_button(curr_send_seq)
                last_update_time = now
            else:
                await asyncio.sleep(1.0) # idle time
        LOGGER.debug("Exit CAN send taks")

    async def can_start_update(self):
        """Start receiving"""
        LOGGER.debug("Starting CAN bus")
        try:
            self._notifier = can.Notifier(self._can, self._can_listeners, loop=self._hass.loop)
        except Exception as error:
            LOGGER.error("Failed to init can bus notifier. Error:" + str(error) + str(type(self._hass)))
            return
        self._send_running = True
        self._button_send_task = self._hass.async_create_background_task(self.send_loop(),"send_button_sequence_task")
        LOGGER.debug("Started CAN bus background task")

    async def can_stop_update(self):
        """Stop receiving"""
        LOGGER.debug("Stopping CAN bus")
        self._notifier.stop()
        await asyncio.sleep(0.1)
        self._send_running = False

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
            except Exception as error:
                LOGGER.warning("Fail to set display address: " +  str(error))
                self._lcd_addr = 0x80
        else:
            LOGGER.warning("Wrong display message length: " + str(msg.dlc))

    def parse_lcd(self):
        """"Try to find name, value unit pairs in current display line"""
        for cur_line in range(4):
            try:
                # get the current lcd line and create string of it
                cur_lcd_line = ''.join(self._lcd_buf[lcd_line_addr[cur_line]:lcd_line_addr[cur_line]+19])
            except:
                LOGGER.error("Fail to join lcd line: " + str(error) + " Current-LCDline:" + str(cur_line) +  " Address: " + str(self._lcd_addr))
                continue
            try:
                splitted = re.split(r'([-]?\d+[.\d]*)', cur_lcd_line)
                name = ''.join(splitted[0:(len(splitted)-2)]).strip()
                value = splitted[-2].strip()
                unit = splitted[-1].strip()
                # Handle some special names:
                if name == "Heizungspumpe":
                    name = name+value
                    value = unit
                    unit = "None"
                if name == "HEIZZEITEN":
                    # ignore
                    continue
                name = slugify.slugify(name, separator="_")
                LOGGER.debug("Name: " + str(name) + " Value: " + str(value) + " Unit: " + str(unit) + " LCD Line: " + cur_lcd_line)
            # create or update the sensor
            except Exception as error:
                # could happen for generic display text without a value
                if cur_lcd_line.find("Kessel") == 0:
                    name = "kessel_status"
                    value = cur_lcd_line
                    unit = "None"
                else:
                    LOGGER.debug("Exception during parsing lcd line " + str(cur_line) + " :" + str(error) + " Current-LCDline:" + cur_lcd_line)
                    continue
            try:
                sensor_entry = self._registered_values[name]
            except:
                # instantiate the sensor
                entity_description = SENSORS.get(name)
                if entity_description:
                    LOGGER.debug("Adding sensor: Name: " + str(name) + " Value: " + str(value) + " Unit: " + str(unit))
                    frlng_sens = FrlngEntity(self._dev_id, entity_description, name, unit, value)
                    self._registered_values[name] = frlng_sens
                    self._async_add_entities([frlng_sens], update_before_add=True)
                else:
                    LOGGER.debug("No entity description available for: " +  name)    
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
        self._pause_buttonsseq = True
        return

    def handle_time_data(self, msg):
        """Callback for time messages"""
        return

class FrlngEntity(SensorEntity):
    """Entity reading values from fröling can lcd display message."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    
    def __init__(self, dev_id, entity_description, name, unit, value):
        """Initialize a Fröling Entity."""
        self._dev_id = dev_id
        self.my_name = name
        self.my_unit = unit
        self.my_value = value
        self._async_remove_dispatcher = None
        self.entity_description = entity_description
        self._attr_unique_id = f"{dev_id}_{name}"
        #self._attr_name = f"{name}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev_id)},
            name=DEFAULT_DEVICE_NAME,
        )

    def get_unique_id(self):
        return self._attr_unique_id

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""

        @callback
        def handle_new_value(name, value, unit):
            """Update value and update stat if changed"""
            assert self.my_name == name
            assert self.my_unit == unit
            if self.my_value == value:
                return
            self.my_value = value
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
        return self.my_value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return SENSOR_UNIT_MAPPING[self.my_unit]
