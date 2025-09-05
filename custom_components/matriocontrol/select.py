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
    # Create entities for all 8 zones - names will be updated from coordinator data
    for zone_id in range(1, 9):
        entities.append(MatrioControlInputSelect(coordinator, zone_id))
    
    async_add_entities(entities)


class MatrioControlInputSelect(MatrioControlEntity, SelectEntity):
    """Representation of a Matrio zone input selection."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the input select."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_input"

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        zone_name = zone_names.get(self.zone_id, f"Zone {self.zone_id}")
        return f"{zone_name} Input"

    @property
    def options(self) -> list[str]:
        """Return the list of available options."""
        # Use input_mappings if available, otherwise fall back to inputs
        input_mappings = self.coordinator.data.get("input_mappings", {})
        if input_mappings:
            return list(input_mappings.values())
        
        inputs = self.coordinator.data.get("inputs", {})
        return list(inputs.values()) if inputs else []

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        # Return None to indicate unknown state - this allows input selection
        # In a full implementation, this would track actual device state
        return None

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _LOGGER.debug("async_select_option called: zone_id=%s, option='%s'", self.zone_id, option)
        
        # Find input ID by name using input_mappings if available
        input_mappings = self.coordinator.data.get("input_mappings", {})
        if input_mappings:
            # Use input_mappings (device names)
            input_id = None
            for iid, name in input_mappings.items():
                if name == option:
                    input_id = iid
                    break
            _LOGGER.debug("Found input_id=%s using input_mappings", input_id)
        else:
            # Fall back to inputs
            inputs = self.coordinator.data.get("inputs", {})
            input_id = None
            for iid, name in inputs.items():
                if name == option:
                    input_id = iid
                    break
            _LOGGER.debug("Found input_id=%s using inputs fallback", input_id)
        
        if input_id:
            _LOGGER.debug("Calling controller.set_input: zone_id=%s, input_id=%s", self.zone_id, input_id)
            await self.hass.async_add_executor_job(
                self.coordinator.controller.set_input, self.zone_id, input_id
            )
            _LOGGER.debug("Requesting coordinator refresh after input change")
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.warning("Could not find input_id for option '%s'", option)
