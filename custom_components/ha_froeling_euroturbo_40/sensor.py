"""Platform for sensor integration."""
from homeassistant.const import TEMP_CELSIUS
from homeassistant.helpers.entity import Entity
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
import serial
#import serial_asyncio
import threading
from serial import SerialException
import asyncio
from functools import partial
from hexdump import hexdump
from .const import (
    CONF_SERIAL_PORT
)

import logging
_LOGGER = logging.getLogger(__name__)
from enum import StrEnum

class ETAFrame():
    pass

async def async_setup_entry(hass, config_entry, async_add_devices):
    """Set up entry."""
    sensors = [ ETASensor("Kessel Temperatur",      UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x08], 10),
                ETASensor("Puffertemperatur unten", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x0a], 10),
                ETASensor("Puffertemperatur mitte", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x0b], 10),
                ETASensor("Puffertemperatur oben",  UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x0c], 10),
                ETASensor("Außentemperatur",        UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x46], 10),
                ETASensor("Pufferladezustand",      PERCENTAGE,                SensorDeviceClass.BATTERY,     SensorStateClass.MEASUREMENT, [0x00,0x4b], 10),
                ETASensor("Abgastemperatur",        UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x0f], 10),
                ETASensor("Rücklauftemperatur",     UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, [0x00,0x09], 10),]
    async_add_devices(sensors)

    baud_rate=19200
    ttydev=config_entry.data.get(CONF_SERIAL_PORT)
    _LOGGER.debug("Opening " + str(ttydev) + " with: " + str(baud_rate ))
    sercon = ETASerialConnection( ttydev, baud_rate, update_sensors, sensors)
    sercon._serial_loop_task = threading.Thread(target=sercon.serial_read)
    sercon._serial_loop_task.start()
    await asyncio.sleep(1)
    # register for all required sensor values       
    send_data = []
    for sensor in sensors:
        send_data.append(sensor.getETAAddr())
    send_frame = ETAFrame()
    send_frame.createSendFrame(ETAFrame.ETA_COMMAND_CODES.START_SERVICE, send_data)

    await asyncio.sleep(0.1)
    await sercon.sendframe(send_frame)
    await asyncio.sleep(0.1)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, sercon.stop_serial_read)

def update_sensors(sensors, frame : ETAFrame):
    values = frame.getETAData()
    for value in values:
        cur_addr = value.get_data_addr()
        for cur_sensor in sensors:
            if cur_sensor.getETAAddr().get_data_addr() == cur_addr:
                cur_sensor.onNewValue(value)

class ETAFrame():
    class ETA_COMMAND_CODES(StrEnum):
        START_SERVICE    = "MC"
        END_SERVICE      = "ME"
        RESPONSE_SERVICE = "MD"
    class ETA_DATA():
        def __init__(self, data: bytes):
            self._target = 0x08
            if len(data) == 5:
                self._target = data[0]
                self._data_addr = int.from_bytes(data[1:3])
                self._data = int.from_bytes(data[3:5])
            elif len(data) == 2:
                self._data_addr = int.from_bytes(data[1:2])
                self._data = None
            else:
                raise Exception("Data object length not supported")
        def get_data_addr(self):
            return self._data_addr
        def get_data(self):
            return self._data
        def serialize(self):
            if self._data == None:
                return b"".join([self._target.to_bytes(1), self._data_addr.to_bytes(2)])
            else:
                return b"".join([self._target.to_bytes(1), self._data_addr.to_bytes(2), self._data.to_bytes(2)])

    def __init__(self):
        self._eta_cmd_code = None
        self._cmd_code = ""
        self._len = 0
        self._chksm = 0
        self._calc_chksm = 0
        self._interval = 10 # update time in seconds
        self._curr_offset = 0
        self.eta_data_list = []
        self.eta_data_buffer = bytearray(5)

    def createSendFrame(self, func_code : ETA_COMMAND_CODES, data : ETA_DATA):
        self._len = 1 + (len(data) * 3)
        self._eta_cmd_code = func_code
        self._chksm = 0
        self.eta_data_list = data

    def deserialize(self, data : bytes):
        for rec_data in data:
            if self._curr_offset < 2:
                self._cmd_code += str(rec_data.to_bytes().decode("ascii"))
                if self._curr_offset == 1:
                    self._eta_cmd_code = ETAFrame.ETA_COMMAND_CODES(self._cmd_code)
            elif self._curr_offset < 3:
                self._len = rec_data
            elif self._curr_offset < 4:
                self._chksm = rec_data
                self._calc_chksm = 0
            else:
                if self._curr_offset-4 > self._len:
                    raise Exception("Frame length not in range, expected len: " + str(self._len) + " current offset: " + str(self._curr_offset)) 
                self._calc_chksm += int.from_bytes(rec_data.to_bytes())
                self.eta_data_buffer[int((self._curr_offset-4)%5)] = rec_data
                if (self._curr_offset-3) % 5 == 0 and (self._curr_offset-4)>0:
                    self.eta_data_list.append(ETAFrame.ETA_DATA(self.eta_data_buffer))
                if self._curr_offset-3 == self._len:
                    if (self._calc_chksm & 0xff) != self._chksm:
                        raise Exception("Receive checksum error: " + str(self._calc_chksm & 0xff) + " Expected: " + str(self._chksm))
                    return True
            self._curr_offset = self._curr_offset + 1
            return False

    def serialize(self):
        data = bytearray()
        data += self._eta_cmd_code.encode()
        data += self._len.to_bytes(1)
        data += bytes(1) # dummy checksum
        if(self._eta_cmd_code == ETAFrame.ETA_COMMAND_CODES.START_SERVICE):
            data += self._interval.to_bytes(1)
            self._calc_chksm = self._interval
        else:
            self._calc_chksm = 0
        for send_data in self.eta_data_list:
            send_str = send_data.serialize()
            data += send_str
            self._calc_chksm += int(sum(send_str))
        # store final checksum
        data[3] = self._calc_chksm & 0xff
        return data

    def getETAData(self):
        return self.eta_data_list
    def getCMDCode(self):
        return self._cmd_code


class ETASerialConnection():
    """serial class."""
    def __init__(
        self,
        port,
        baudrate,
        udpdate_sensors_cb,
        sensors
    ):
        """Initialize the Serial connection."""
        self._state = None
        self._port = port
        self._baudrate = baudrate
        self._serial_loop_task = None
        self._running = True
        try:
            self.ser = serial.Serial(self._port, self._baudrate, timeout=0.1)
        except Exception as error:
            _LOGGER.error("Failed to init serial port: " + str(error))
        self.current_frame = None
        self._complete = False
        self._udpdate_sensors_cb = udpdate_sensors_cb
        self._sensors = sensors
    def serial_read(
        self    ):
        """Read the data from the port."""
        logged_error = False
        _LOGGER.debug("Entering read loop")
        while self._running:
            data = self.ser.read(1000)
            if len(data):
                _LOGGER.debug("Received (" + str(len(data)) + "):")
                _LOGGER.debug(hexdump(data, result='return'))
                for recbyte in data:
                    if recbyte == ord('{') and self.current_frame == None:
                        self.current_frame = ETAFrame()
                        continue
                    if self.current_frame != None and self._complete  == False:
                        try:
                            self._complete = self.current_frame.deserialize(recbyte.to_bytes(1))
                        except Exception as error:
                            _LOGGER.error("Framing error: " + str(error))
                            self.current_frame = None
                        if self._complete == True:
                            continue
                    if self._complete == True:
                        if recbyte == ord('}'):
                            if self.current_frame.getCMDCode() == ETAFrame.ETA_COMMAND_CODES.RESPONSE_SERVICE:
                                self._udpdate_sensors_cb(self._sensors, self.current_frame)
                            else:
                                _LOGGER.warning("Unexpexted cmd code received")
                        else:
                            _LOGGER.error("Failed to find EOF")
                        self._complete = False
                        self.current_frame = None
        _LOGGER.debug("Exiting read loop")
    @callback
    def stop_serial_read(self, event):
        """Close resources."""
        _LOGGER.info("Closing serial receive thread")
        self._running = False
        self._serial_loop_task.join()
        
    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def extra_state_attributes(self):
        """Return the attributes of the entity (if any JSON present)."""
        return self._attributes

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
    
    async def sendframe(self, data : ETAFrame):
        sendbuf = data.serialize()
        send_data = bytearray()
        send_data = b'{' + sendbuf + b'}'
        _LOGGER.debug("Sending (" + str(len(send_data)) + "):")
        _LOGGER.debug(hexdump(send_data, result='return'))
        size = self.ser.write(send_data)
        self.ser.flush()

class ETASensor(SensorEntity):
    """ETA Sensor entity."""
    _attr_should_poll = True
    _attr_name = "default"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0
    _attr_native_factor = 1.0
    _attr_eta_data_addr = None
    def __init__(self, name, unit, dev_class, state_class, eta_data_addr, factor):
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_state_class = state_class
        self._attr_eta_data_addr = ETAFrame.ETA_DATA(eta_data_addr)
        self._attr_native_factor = factor
    def onNewValue(self, data : ETAFrame.ETA_DATA):
        try:
            self._attr_native_value = data.get_data()/self._attr_native_factor
        except:
            # pin value to zero if e.g. due to divide by zero
            self._attr_native_value = 0
        self.async_write_ha_state()
    
    def getETAAddr(self):
        return self._attr_eta_data_addr
