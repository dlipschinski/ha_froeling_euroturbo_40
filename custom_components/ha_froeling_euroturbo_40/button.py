"""Button platform for the Fröling integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .sensor import BUTTON_TYPES, FrlngButtonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
):
    """Set up the Fröling button entity."""
    device = hass.data.get(DOMAIN)
    if device is None:
        return

    async_add_entities([FrlngButtonEntity(device, BUTTON_TYPES[0])])
