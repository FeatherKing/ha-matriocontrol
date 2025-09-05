"""Media player platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, INPUTS, ZONES, VOLUME_MAX
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the media player platform."""
    coordinator: MatrioControlDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    # Create entities for all 8 zones - names will be updated from coordinator data
    for zone_id in range(1, 9):
        entities.append(MatrioControlMediaPlayer(coordinator, zone_id))
    
    async_add_entities(entities)


class MatrioControlMediaPlayer(MatrioControlEntity, MediaPlayerEntity):
    """Representation of a Matrio zone as a media player."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the media player."""
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_zone_{zone_id}"
        self._attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
        )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zone_names = self.coordinator.data.get("zone_names", {})
        return zone_names.get(self.zone_id, f"Zone {self.zone_id}")

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        # For now, assume device is always on when connected
        # In a full implementation, this would track actual zone power state
        if self.coordinator.data.get("connected", False):
            return MediaPlayerState.ON
        return MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        """Return the list of available input sources."""
        # Use input_mappings if available, otherwise fall back to inputs
        input_mappings = self.coordinator.data.get("input_mappings", {})
        if input_mappings:
            return list(input_mappings.values())
        
        inputs = self.coordinator.data.get("inputs", INPUTS)
        return list(inputs.values())

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        # This would be determined by actual device state
        # For now, return the first input as default
        inputs = self.coordinator.data.get("inputs", INPUTS)
        return list(inputs.values())[0] if inputs else None

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        # This would be determined by actual device state
        # For now, return a default value
        return 0.5

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        # This would be determined by actual device state
        return False

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_power, self.zone_id, True
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_zone_power, self.zone_id, False
        )
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert from 0..1 to 0..38 range used by MatrioController
        volume_level = int(volume * VOLUME_MAX)
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_volume, self.zone_id, volume_level
        )
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self.hass.async_add_executor_job(
            self.coordinator.controller.set_mute, self.zone_id, mute
        )
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        # Find input ID by name using input_mappings if available
        input_mappings = self.coordinator.data.get("input_mappings", {})
        if input_mappings:
            # Use input_mappings (device names)
            input_id = None
            for iid, name in input_mappings.items():
                if name == source:
                    input_id = iid
                    break
        else:
            # Fall back to inputs
            inputs = self.coordinator.data.get("inputs", INPUTS)
            input_id = None
            for iid, name in inputs.items():
                if name == source:
                    input_id = iid
                    break
        
        if input_id:
            await self.hass.async_add_executor_job(
                self.coordinator.controller.set_input, self.zone_id, input_id
            )
            await self.coordinator.async_request_refresh()