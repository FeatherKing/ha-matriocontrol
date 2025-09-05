"""Sensor platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ZONES
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    
    # Add device status sensor
    entities.append(MatrioControlDeviceStatusSensor(coordinator))
    
    # Add zone name sensors
    for zone_id, zone_name in ZONES.items():
        entities.append(MatrioControlZoneNameSensor(coordinator, zone_id, zone_name))
    
    async_add_entities(entities)


class MatrioControlDeviceStatusSensor(MatrioControlEntity, SensorEntity):
    """Representation of the Matrio device connection status."""

    def __init__(self, coordinator: MatrioControlDataUpdateCoordinator) -> None:
        """Initialize the device status sensor."""
        super().__init__(coordinator, 0)  # Use zone 0 for device-level sensor
        self._attr_name = "Matrio Device Status"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_device_status"
        self._attr_icon = "mdi:audio-video"

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        if self.coordinator.data.get("connected", False):
            return "Connected"
        return "Disconnected"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        device_info = self.coordinator.data.get("device_info", {})
        return {
            "device_name": device_info.get("device_name", "Unknown"),
            "mac_address": device_info.get("mac_address", "Unknown"),
            "firmware": device_info.get("firmware", "Unknown"),
            "hardware": device_info.get("hardware", "Unknown"),
            "last_heartbeat": self.coordinator.data.get("last_heartbeat", False),
        }


class MatrioControlZoneNameSensor(MatrioControlEntity, SensorEntity):
    """Representation of a Matrio zone name sensor."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the zone name sensor."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Name"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_name"
        self._attr_icon = "mdi:speaker"

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        zones = self.coordinator.data.get("zones", {})
        zone_key = f"zone_{self.zone_id}"
        return zones.get(zone_key, f"Zone {self.zone_id}")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "zone_id": self.zone_id,
            "zone_number": self.zone_id,
        }
