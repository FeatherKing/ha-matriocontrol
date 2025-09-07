"""Number platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, ZONES, BALANCE_MIN, BALANCE_MAX, BASS_TREBLE_MIN, BASS_TREBLE_MAX
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    # Create entities for all 8 zones - names will be updated from coordinator data
    for zone_id in range(1, 9):
        entities.extend([
            MatrioControlBassNumber(coordinator, zone_id),
            MatrioControlTrebleNumber(coordinator, zone_id),
            MatrioControlBalanceNumber(coordinator, zone_id),
        ])
    
    async_add_entities(entities)


class MatrioControlBassNumber(MatrioControlEntity, NumberEntity):
    """Representation of a Matrio zone bass control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the bass number."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_bass"
        self._attr_native_min_value = BASS_TREBLE_MIN
        self._attr_native_max_value = BASS_TREBLE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        zone_name = zone_names.get(self.zone_id, f"Zone {self.zone_id}")
        return f"{zone_name} Bass"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        if zone_state and "bass" in zone_state:
            return float(zone_state["bass"])
        
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_bass, self.zone_id, int(value)
        )
        await self.coordinator.async_request_refresh()


class MatrioControlTrebleNumber(MatrioControlEntity, NumberEntity):
    """Representation of a Matrio zone treble control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the treble number."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_treble"
        self._attr_native_min_value = BASS_TREBLE_MIN
        self._attr_native_max_value = BASS_TREBLE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        zone_name = zone_names.get(self.zone_id, f"Zone {self.zone_id}")
        return f"{zone_name} Treble"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        if zone_state and "treble" in zone_state:
            return float(zone_state["treble"])
        
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_treble, self.zone_id, int(value)
        )
        await self.coordinator.async_request_refresh()


class MatrioControlBalanceNumber(MatrioControlEntity, NumberEntity):
    """Representation of a Matrio zone balance control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the balance number."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_balance"
        self._attr_native_min_value = BALANCE_MIN
        self._attr_native_max_value = BALANCE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        zone_name = zone_names.get(self.zone_id, f"Zone {self.zone_id}")
        return f"{zone_name} Balance"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        if zone_state and "balance" in zone_state:
            # Convert balance string to numeric value
            balance_str = zone_state["balance"]
            if balance_str == "MAX Right":
                return 100.0
            elif balance_str == "MAX Left":
                return -100.0
            elif balance_str == "Default" or balance_str == "Center":
                return 0.0
            else:
                # Try to parse as numeric value
                try:
                    return float(balance_str)
                except (ValueError, TypeError):
                    return 0.0
        
        return 0.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_balance, self.zone_id, int(value)
        )
        await self.coordinator.async_request_refresh()
