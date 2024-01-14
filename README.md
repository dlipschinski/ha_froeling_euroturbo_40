
![Logo](https://www.froeling.com/de-de/wp-content/uploads/sites/7/2020/09/logo_froeling-300x71.png)]
# Fröling Home Assistant integration

I have written this integration for my 20year old wood heating (Fröling Supramat 40). 
The integration works by emulating button pressures (sending CAN messages) and parsing the CAN bus message which is transmitted from the main unit to the display unit.
Many the button sequence tries to hit all available display pages.
Newer version of Fröling (or ETA) heating system have dedicated serial interfaces which can be used to readout measurement values (e.g. http://ulrich-franzke.de/haustechnik/eta_programm1.html).

The skeleton was copied from https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/tree/master
The config flow and entity approach is copied from https://github.com/home-assistant/core/tree/dev/homeassistant/components/edl21
This integration is using python-can with in asyncio mode.

# Setup for MCP2515

To enable MCP2515 drivers add following to the file /mng/boot/config.txt:

```
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
dtoverlay=spi-bcm2835-overlay
```

Connect the MSP2515 to SPI of the RPI (in my case RPI4B) and the interrupt pin to GPIO25.

# Precondition CAN Socket: 

When running a hassos on a rasperry you need to enable (link up) your CAN network interface (in my case i use a mcp2515). 
Therefore create a udev folder in a usb drive and create a file called 80-can.rules
Add following line to the file:
```
ACTION=="add", SUBSYSTEM=="net", ENV{INTERFACE}=="can*", RUN+="/sbin/ip link set $name type can bitrate 250000", RUN+="/sbin/ip link set up $name"
```
This will "link-up" all CAN interfaces with 250kBit/s during bootup.
See also https://github.com/home-assistant/operating-system/blob/dev/Documentation/configuration.md