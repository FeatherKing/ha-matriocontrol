"""Binary sensor platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        MatrioControlDeviceStatusBinarySensor(coordinator),
    ]
    
    async_add_entities(entities)


class MatrioControlDeviceStatusBinarySensor(MatrioControlEntity, BinarySensorEntity):
    """Representation of a DAX88 device connectivity status."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator
    ) -> None:
        """Initialize the device status binary sensor."""
        super().__init__(coordinator, 0)  # Use zone 0 for device-level sensor
        self._attr_name = "Device Status"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_device_status"
        self._attr_device_class = "connectivity"

    @property
    def is_on(self) -> bool | None:
        """Return true if the device is connected and responding."""
        # Check if the coordinator has recent data and connection is active
        if not self.coordinator.data:
            return False
        
        # Check if we have a connection to the device
        return self.coordinator.data.get("connected", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {}
        
        if self.coordinator.data:
            # Add device information as attributes
            device_info = self.coordinator.data.get("device_info", {})
            if device_info:
                attrs.update({
                    "device_name": device_info.get("device_name"),
                    "mac_address": device_info.get("mac_address"),
                    "firmware": device_info.get("firmware"),
                    "hardware": device_info.get("hardware"),
                })
            
            # Add connection status
            attrs["last_update"] = self.coordinator.last_update_success
            attrs["connection_status"] = "connected" if self.is_on else "disconnected"
        
        return attrs
