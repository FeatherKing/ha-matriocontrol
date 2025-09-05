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
    
    # Add zone name text entities for all 8 zones - names will be updated from coordinator data
    for zone_id in range(1, 9):
        entities.append(MatrioControlZoneNameText(coordinator, zone_id))
    
    async_add_entities(entities)


class MatrioControlZoneNameText(MatrioControlEntity, TextEntity):
    """Representation of a Matrio zone name text input."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the zone name text."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_name"
        self._attr_native_max_length = 20  # Reasonable limit for zone names
        self._attr_mode = TextMode.TEXT

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        zone_name = zone_names.get(self.zone_id, f"Zone {self.zone_id}")
        return f"{zone_name} Name"

    @property
    def native_value(self) -> str | None:
        """Return the current value."""
        zone_names = self.coordinator.data.get("zone_names", {})
        return zone_names.get(self.zone_id, f"Zone {self.zone_id}")

    async def async_set_value(self, value: str) -> None:
        """Set the zone name."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_name, self.zone_id, value
        )
        await self.coordinator.async_request_refresh()


