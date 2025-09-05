"""Number platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ZONES, BALANCE_MIN, BALANCE_MAX, BASS_TREBLE_MIN, BASS_TREBLE_MAX, VOLUME_MIN, VOLUME_MAX
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
    for zone_id, zone_name in ZONES.items():
        entities.extend([
            MatrioControlVolumeNumber(coordinator, zone_id, zone_name),
            MatrioControlBassNumber(coordinator, zone_id, zone_name),
            MatrioControlTrebleNumber(coordinator, zone_id, zone_name),
            MatrioControlBalanceNumber(coordinator, zone_id, zone_name),
        ])
    
    async_add_entities(entities)


class MatrioControlVolumeNumber(MatrioControlEntity, NumberEntity):
    """Representation of a Matrio zone volume control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the volume number."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Volume"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_volume"
        self._attr_native_min_value = VOLUME_MIN
        self._attr_native_max_value = VOLUME_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # This would be determined by actual device state
        return 0

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_volume, self.zone_id, int(value)
        )
        await self.coordinator.async_request_refresh()


class MatrioControlBassNumber(MatrioControlEntity, NumberEntity):
    """Representation of a Matrio zone bass control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the bass number."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Bass"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_bass"
        self._attr_native_min_value = BASS_TREBLE_MIN
        self._attr_native_max_value = BASS_TREBLE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # This would be determined by actual device state
        return 0

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
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the treble number."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Treble"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_treble"
        self._attr_native_min_value = BASS_TREBLE_MIN
        self._attr_native_max_value = BASS_TREBLE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # This would be determined by actual device state
        return 0

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
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the balance number."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Balance"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_balance"
        self._attr_native_min_value = BALANCE_MIN
        self._attr_native_max_value = BALANCE_MAX
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        # This would be determined by actual device state
        return 0

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_balance, self.zone_id, int(value)
        )
        await self.coordinator.async_request_refresh()