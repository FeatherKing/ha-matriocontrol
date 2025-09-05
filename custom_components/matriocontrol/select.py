"""Select platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
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
    """Set up the select platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for zone_id, zone_name in ZONES.items():
        entities.append(MatrioControlInputSelect(coordinator, zone_id, zone_name))
    
    async_add_entities(entities)


class MatrioControlInputSelect(MatrioControlEntity, SelectEntity):
    """Representation of a Matrio zone input selection."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the input select."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Input"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_input"

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        inputs = self.coordinator.data.get("inputs", {})
        return list(inputs.values()) if inputs else []

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        # This would be determined by actual device state
        # For now, return the first available option
        options = self.options
        return options[0] if options else None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        # Find input ID by name
        inputs = self.coordinator.data.get("inputs", {})
        input_id = None
        for iid, name in inputs.items():
            if name == option:
                input_id = iid
                break
        
        if input_id:
            await self.hass.async_add_executor_job(
                self.coordinator.controller.set_input, self.zone_id, input_id
            )
            await self.coordinator.async_request_refresh()
