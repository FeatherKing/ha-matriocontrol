"""Switch platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up the switch platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    for zone_id, zone_name in ZONES.items():
        entities.extend([
            MatrioControlZoneSwitch(coordinator, zone_id, zone_name),
            MatrioControlMuteSwitch(coordinator, zone_id, zone_name),
        ])
    
    async_add_entities(entities)


class MatrioControlZoneSwitch(MatrioControlEntity, SwitchEntity):
    """Representation of a Matrio zone power switch."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the zone switch."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Power"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_power"

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        # This would be determined by actual device state
        # For now, return None to indicate unknown state
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone on."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_power, self.zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone off."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_power, self.zone_id, False
        )
        await self.coordinator.async_request_refresh()


class MatrioControlMuteSwitch(MatrioControlEntity, SwitchEntity):
    """Representation of a Matrio zone mute switch."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int, 
        zone_name: str
    ) -> None:
        """Initialize the mute switch."""
        super().__init__(coordinator, zone_id)
        self._attr_name = f"{zone_name} Mute"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}_mute"

    @property
    def is_on(self) -> bool | None:
        """Return true if the zone is muted."""
        # This would be determined by actual device state
        # For now, return None to indicate unknown state
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the zone."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_mute, self.zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the zone."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_mute, self.zone_id, False
        )
        await self.coordinator.async_request_refresh()
