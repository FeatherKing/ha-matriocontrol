"""The Matrio Control integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, DEFAULT_PORT, CONF_CHILD_ENTITY_MAPPINGS
from .coordinator import MatrioControlDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.BINARY_SENSOR,
]

# YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.All(
            cv.ensure_list,
            [
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): cv.string,
                        vol.Optional(CONF_PORT, default=DEFAULT_PORT): cv.port,
                        vol.Optional(CONF_CHILD_ENTITY_MAPPINGS, default={}): vol.Schema(
                            {cv.string: cv.entity_id}
                        ),
                    }
                )
            ],
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Matrio Control integration from YAML configuration."""
    if DOMAIN not in config:
        return True

    for device_config in config[DOMAIN]:
        # Store source mappings in hass.data for access by config entry setup
        hass.data.setdefault(DOMAIN, {})
        device_key = f"{device_config[CONF_HOST]}:{device_config.get(CONF_PORT, DEFAULT_PORT)}"
        hass.data[DOMAIN][f"yaml_{device_key}"] = {
            CONF_CHILD_ENTITY_MAPPINGS: device_config.get(CONF_CHILD_ENTITY_MAPPINGS, {})
        }
        _LOGGER.debug("Stored YAML child entity mappings for %s: %s", device_key, device_config.get(CONF_CHILD_ENTITY_MAPPINGS, {}))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Matrio Control from a config entry."""
    coordinator = MatrioControlDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok



