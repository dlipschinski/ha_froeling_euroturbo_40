# Fröling Home Assistant integration

The skeleton was copied from https://github.com/MatthewFlamm/pytest-homeassistant-custom-component/tree/master
The config flow is copied from https://github.com/home-assistant/core/tree/dev/homeassistant/components/edl21
Currently the component starts a thread to call the serial read function, tried it by using serial_asyncio without success.

Precondition: 
 create a udev folder in a usb drive and create a file called 80-can.rules
ACTION=="add", SUBSYSTEM=="net", ENV{INTERFACE}=="can*", RUN+="/sbin/ip link set $name type can bitrate 250000", RUN+="/sbin/ip link set up $name"
See also https://github.com/home-assistant/operating-system/blob/dev/Documentation/configuration.md