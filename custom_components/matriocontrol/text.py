"""Text platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INPUTS, ZONES
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the text platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    
    # Add zone name text entities
    for zone_id, zone_name in ZONES.items():
        entities.append(MatrioControlZoneNameText(coordinator, zone_id, zone_name))
    
    # Add input name text entities
    for input_id, input_name in INPUTS.items():
        entities.append(MatrioControlInputNameText(coordinator, input_id, input_name))
    
    async_add_entities(entities)


class MatrioControlZoneNameText(MatrioControlEntity, TextEntity):
    """Representation of a Matrio zone name text input."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the zone name text."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Name"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_name"
        self._attr_native_max_length = 20  # Reasonable limit for zone names
        self._attr_mode = TextMode.TEXT
        # Get current zone name from coordinator data
        zones = coordinator.data.get("zones", {})
        zone_key = f"zone_{zone_id}"
        self._attr_native_value = zones.get(zone_key, zone_name)

    async def async_set_value(self, value: str) -> None:
        """Set the zone name."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_name, self.zone_id, value
        )
        await self.coordinator.async_request_refresh()


class MatrioControlInputNameText(MatrioControlEntity, TextEntity):
    """Representation of a Matrio input name text input."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        input_id: int, 
        input_name: str
    ) -> None:
        """Initialize the input name text."""
        super().__init__(coordinator, input_id)
        self._attr_name = f"Input {input_id} Name"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_input_{input_id}_name"
        self._attr_native_max_length = 20  # Reasonable limit for input names
        self._attr_mode = TextMode.TEXT
        # Get current input name from coordinator data
        inputs = coordinator.data.get("inputs", {})
        self._attr_native_value = inputs.get(input_id, input_name)

    async def async_set_value(self, value: str) -> None:
        """Set the input name."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_input_name, self.zone_id, value
        )
        await self.coordinator.async_request_refresh()
