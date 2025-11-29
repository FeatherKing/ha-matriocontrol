"""Media player platform for Matrio Control."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaPlayerDeviceClass,
    MediaType,
    BrowseMedia,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import entity_registry as er

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
        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._current_child_entity_id = None
        
        # Base receiver features always available
        base_features = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
        )
        
        self._base_features = base_features
        self._attr_supported_features = self._base_features
        
        # Initialize child entity tracking (but defer feature update until hass is available)
        self._current_child_entity_id = self._get_child_entity_id()

    def _get_child_entity_id(self) -> str | None:
        """Get the current child entity ID based on selected input."""
        child_entity_mappings = self.coordinator.data.get("child_entity_mappings", {})
        _LOGGER.debug("Zone %d _get_child_entity_id: child_entity_mappings=%s", 
                     self.zone_id, child_entity_mappings)
        
        if not child_entity_mappings:
            _LOGGER.debug("Zone %d no child_entity_mappings found", self.zone_id)
            return None
        
        # Get current zone input
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        _LOGGER.debug("Zone %d zone_state=%s", self.zone_id, zone_state)
        
        if not zone_state:
            _LOGGER.debug("Zone %d no zone_state found", self.zone_id)
            return None
            
        # Get input number from zone state
        current_input = zone_state.get("input_number")
        _LOGGER.debug("Zone %d current_input=%s", self.zone_id, current_input)
        
        if current_input is None:
            _LOGGER.debug("Zone %d no current_input found", self.zone_id)
            return None
        
        # Convert to input_N format to match configuration
        input_key = f"input_{current_input}"
        result = child_entity_mappings.get(input_key)
        
        _LOGGER.debug("Zone %d input_key=%s -> child_entity=%s", 
                     self.zone_id, input_key, result)
        
        # Update cached child entity ID if it changed
        if result != self._current_child_entity_id:
            old_child = self._current_child_entity_id
            self._current_child_entity_id = result
            _LOGGER.debug("Zone %d child entity changed: %s -> %s", 
                         self.zone_id, old_child, result)
            
            # Update supported features when child entity changes
            self._update_supported_features()
        
        # Look up mapped child entity
        return result
    
    def _get_child_entity(self):
        """Get the child media player entity object."""
        # Safety check - hass not available during initialization
        if not self.hass:
            return None
            
        # Use cached child entity ID to avoid timing issues during source changes
        child_entity_id = self._current_child_entity_id
        if not child_entity_id:
            return None
            
        # Get state from hass.states
        return self.hass.states.get(child_entity_id)
    
    def _update_supported_features(self):
        """Update supported features based on child entity capabilities."""
        child_entity = self._get_child_entity()
        child_entity_id = self._current_child_entity_id
        
        _LOGGER.debug("Zone %d _update_supported_features: child_entity_id=%s, child_entity=%s", 
                     self.zone_id, child_entity_id, child_entity is not None)
        
        if child_entity and child_entity.state != "unavailable":
            # Get child entity's actual supported features
            child_features = child_entity.attributes.get("supported_features", 0)
            
            _LOGGER.debug("Zone %d child %s has features=0x%x", 
                         self.zone_id, child_entity_id, child_features)
            
            # Combine base receiver features with child's media playback features
            # Filter child features to only include ones that make sense to pass through
            allowed_child_features = (
                MediaPlayerEntityFeature.PLAY |
                MediaPlayerEntityFeature.PAUSE |
                MediaPlayerEntityFeature.STOP |
                MediaPlayerEntityFeature.PREVIOUS_TRACK |
                MediaPlayerEntityFeature.NEXT_TRACK |
                MediaPlayerEntityFeature.SEEK |
                MediaPlayerEntityFeature.REPEAT_SET |
                MediaPlayerEntityFeature.SHUFFLE_SET |
                MediaPlayerEntityFeature.CLEAR_PLAYLIST |
                MediaPlayerEntityFeature.PLAY_MEDIA |
                MediaPlayerEntityFeature.GROUPING
            )
            
            # Only pass through features the child actually supports
            passthrough_features = child_features & allowed_child_features
            self._attr_supported_features = self._base_features | passthrough_features
            
            _LOGGER.debug("Zone %d features: base=0x%x, child=0x%x, allowed=0x%x, final=0x%x", 
                         self.zone_id, self._base_features, child_features, 
                         passthrough_features, self._attr_supported_features)
        else:
            self._attr_supported_features = self._base_features
            _LOGGER.debug("Zone %d no child entity or unavailable, using base features=0x%x", 
                         self.zone_id, self._base_features)
    
    @callback
    def _child_entity_changed(self, event):
        """Handle child entity state changes."""
        if event.data["entity_id"] == self._current_child_entity_id:
            _LOGGER.debug("Zone %d child entity %s state changed", 
                         self.zone_id, self._current_child_entity_id)
            
            # Check if group membership changed
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            
            if old_state and new_state:
                old_group = old_state.attributes.get("group_members", [])
                new_group = new_state.attributes.get("group_members", [])
                old_features = old_state.attributes.get("supported_features", 0)
                new_features = new_state.attributes.get("supported_features", 0)
                old_available = old_state.state != "unavailable"
                new_available = new_state.state != "unavailable"
                
                if old_group != new_group:
                    # Child entity group changed - update our zone group accordingly
                    self.hass.async_create_task(self._sync_with_child_group())
                    
                if old_features != new_features or old_available != new_available:
                    # Child entity supported features changed or availability changed - update our features
                    self._update_supported_features()
            
            self.async_write_ha_state()
    
    async def _sync_with_child_group(self):
        """Synchronize zone group with child entity group."""
        child_entity = self._get_child_entity()
        if not child_entity:
            return
        
        child_group_members = child_entity.attributes.get("group_members", [])
        
        # Find all zones that should be in the same group (using same child entities)
        target_zone_members = []
        for entity in self.coordinator._entities:
            if (hasattr(entity, '_get_child_entity_id') and 
                hasattr(entity, 'entity_id') and
                entity._get_child_entity_id() in child_group_members):
                target_zone_members.append(entity.entity_id)
        
        # Join zones together if we have multiple
        if len(target_zone_members) > 1 and self.entity_id in target_zone_members:
            # Use Home Assistant's native grouping for zones
            await self.hass.services.async_call(
                "media_player", "join", {
                    "entity_id": self.entity_id,
                    "group_members": target_zone_members
                }
            )

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zones = self.coordinator.data.get("zones", {})
        zone_key = f"zone_{self.zone_id}"
        zone_name = zones.get(zone_key, f"Zone {self.zone_id}")
        _LOGGER.debug("Media player Zone %d name: %s (zones data: %s)", self.zone_id, zone_name, zones)
        return zone_name

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        if not self.coordinator.data.get("connected", False):
            return MediaPlayerState.OFF
        
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        # If zone is off, return OFF regardless of child state
        if zone_state and zone_state.get("power") == "OFF":
            return MediaPlayerState.OFF
        elif not zone_state or zone_state.get("power") != "ON":
            return MediaPlayerState.OFF
            
        # Zone is ON - check if we have child entity for enhanced state
        child_entity = self._get_child_entity()
        if child_entity and child_entity.state != "unavailable":
            # Delegate state to child entity when available
            child_state = child_entity.state
            if child_state == "playing":
                return MediaPlayerState.PLAYING
            elif child_state == "paused":
                return MediaPlayerState.PAUSED
            elif child_state == "idle":
                return MediaPlayerState.IDLE
            elif child_state == "off":
                return MediaPlayerState.ON  # Zone is on, but child is off
            else:
                return MediaPlayerState.ON
        else:
            # No child entity - basic receiver mode
            return MediaPlayerState.ON

    @property
    def media_content_id(self) -> str | None:
        """Return the content ID of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_content_id")
        return None
    
    @property
    def media_content_type(self) -> str | None:
        """Return the content type of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_content_type")
        return None
    
    @property
    def media_duration(self) -> int | None:
        """Return the duration of current playing media in seconds."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_duration")
        return None
    
    @property
    def media_position(self) -> int | None:
        """Return the position of current playing media in seconds."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_position")
        return None
    
    @property
    def media_position_updated_at(self):
        """Return the time media position was last updated."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_position_updated_at")
        return None
    
    @property
    def media_image_url(self) -> str | None:
        """Return the image URL of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("entity_picture")
        return None
    
    @property
    def media_image_remotely_accessible(self) -> bool:
        """Return if the image is remotely accessible."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_image_remotely_accessible", False)
        return False
    
    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        _LOGGER.debug("Zone %d media_title property accessed", self.zone_id)
        child_entity = self._get_child_entity()
        if child_entity:
            title = child_entity.attributes.get("media_title")
            _LOGGER.debug("Zone %d media_title: %s (child: %s)", 
                         self.zone_id, title, self._current_child_entity_id)
            return title
        _LOGGER.debug("Zone %d media_title: None (no child: %s)", 
                     self.zone_id, self._current_child_entity_id)
        return None
    
    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_artist")
        return None
    
    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_album_name")
        return None
    
    @property
    def media_album_artist(self) -> str | None:
        """Return the album artist of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_album_artist")
        return None
    
    @property
    def media_track(self) -> int | None:
        """Return the track number of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_track")
        return None
    
    @property
    def media_series_title(self) -> str | None:
        """Return the series title of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_series_title")
        return None
    
    @property
    def media_season(self) -> str | None:
        """Return the season of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_season")
        return None
    
    @property
    def media_episode(self) -> str | None:
        """Return the episode of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_episode")
        return None
    
    @property
    def media_channel(self) -> str | None:
        """Return the channel of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_channel")
        return None
    
    @property
    def media_playlist(self) -> str | None:
        """Return the playlist of current playing media."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get("media_playlist")
        return None

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
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        _LOGGER.debug("Zone %d source check - zone_states: %s, zone_state: %s", 
                     self.zone_id, zone_states, zone_state)
        
        if zone_state and "input" in zone_state:
            _LOGGER.debug("Zone %d returning input: %s", self.zone_id, zone_state["input"])
            return zone_state["input"]
        
        _LOGGER.debug("Zone %d returning None for source", self.zone_id)
        return None

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        _LOGGER.debug("Zone %d volume check - zone_states: %s, zone_state: %s", 
                     self.zone_id, zone_states, zone_state)
        
        if zone_state and "volume" in zone_state:
            # Convert from 0..38 range to 0..1 range
            volume = zone_state["volume"]
            volume_level = volume / VOLUME_MAX if VOLUME_MAX > 0 else 0.0
            _LOGGER.debug("Zone %d returning volume: %s -> %s", self.zone_id, volume, volume_level)
            return volume_level
        
        _LOGGER.debug("Zone %d returning None for volume", self.zone_id)
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get("zone_states", {})
        zone_state = zone_states.get(self.zone_id)
        
        if zone_state and "mute" in zone_state:
            return zone_state["mute"] == "MUTED"
        
        return False

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        await self.coordinator.controller.set_zone_power(self.zone_id, True)
        # State will be updated via broadcast callback

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        await self.coordinator.controller.set_zone_power(self.zone_id, False)
        # State will be updated via broadcast callback

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        # Convert from 0..1 to 0..38 range used by MatrioController
        volume_level = int(volume * VOLUME_MAX)
        await self.coordinator.controller.set_volume(self.zone_id, volume_level)
        # State will be updated via broadcast callback

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        await self.coordinator.controller.set_mute(self.zone_id, mute)
        # State will be updated via broadcast callback

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        _LOGGER.debug("async_select_source called: zone_id=%s, source='%s'", self.zone_id, source)
        
        # Find input ID by name using input_mappings if available
        input_mappings = self.coordinator.data.get("input_mappings", {})
        _LOGGER.debug("input_mappings: %s", input_mappings)
        
        if input_mappings:
            # Use input_mappings (device names)
            input_id = None
            for iid, name in input_mappings.items():
                if name == source:
                    input_id = iid
                    break
            _LOGGER.debug("Found input_id %s using input_mappings", input_id)
        else:
            # Fall back to inputs
            inputs = self.coordinator.data.get("inputs", INPUTS)
            _LOGGER.debug("Using fallback inputs: %s", inputs)
            input_id = None
            for iid, name in inputs.items():
                if name == source:
                    input_id = iid
                    break
            _LOGGER.debug("Found input_id %s using fallback inputs", input_id)
        
        if input_id:
            _LOGGER.debug("Calling controller.set_input(%s, %s)", self.zone_id, input_id)
            await self.coordinator.controller.set_input(self.zone_id, input_id)
            # State will be updated via broadcast callback
            _LOGGER.debug("async_select_source completed for zone %s", self.zone_id)
        else:
            _LOGGER.debug("No input_id found for source '%s'", source)

    async def async_media_play(self) -> None:
        """Send play command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_play", {"entity_id": child_entity_id}
            )
    
    async def async_media_pause(self) -> None:
        """Send pause command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_pause", {"entity_id": child_entity_id}
            )
    
    async def async_media_stop(self) -> None:
        """Send stop command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_stop", {"entity_id": child_entity_id}
            )
    
    async def async_media_previous_track(self) -> None:
        """Send previous track command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_previous_track", {"entity_id": child_entity_id}
            )
    
    async def async_media_next_track(self) -> None:
        """Send next track command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_next_track", {"entity_id": child_entity_id}
            )
    
    async def async_media_seek(self, position: float) -> None:
        """Send seek command to child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "media_seek", {
                    "entity_id": child_entity_id,
                    "seek_position": position
                }
            )
    
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media via child entity."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            await self.hass.services.async_call(
                "media_player", "play_media", {
                    "entity_id": child_entity_id,
                    "media_content_type": media_type,
                    "media_content_id": media_id,
                    **kwargs
                }
            )
    
    async def async_browse_media(
        self, media_content_type: str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia | None:
        """Browse media via child entity."""
        child_entity_id = self._get_child_entity_id()
        if not child_entity_id:
            # No child entity mapped - no browsing available
            return None
        
        # For now, return None to disable browse functionality
        # This is a complex delegation that requires accessing the actual child entity instance
        # TODO: Implement proper browse media delegation
        _LOGGER.debug("Browse media requested for zone %d with child %s - not yet implemented", 
                     self.zone_id, child_entity_id)
        return None
    
    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Set up listener for child entity changes
        self._update_child_entity_listener()
        
        # Update supported features based on current child entity
        self._update_supported_features()
    
    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from hass."""
        # Clean up child entity listener
        if hasattr(self, "_child_entity_listener") and self._child_entity_listener:
            self._child_entity_listener()
        
        await super().async_will_remove_from_hass()
    
    @callback
    def _async_coordinator_updated(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug("Zone %d _async_coordinator_updated called", self.zone_id)
        
        # Check if child entity mapping changed
        new_child_entity_id = self._get_child_entity_id()
        _LOGGER.debug("Zone %d coordinator updated: current=%s, new=%s", 
                     self.zone_id, self._current_child_entity_id, new_child_entity_id)
        
        if new_child_entity_id != self._current_child_entity_id:
            old_child_entity_id = self._current_child_entity_id
            self._current_child_entity_id = new_child_entity_id
            self._update_child_entity_listener()
            
            _LOGGER.info("Zone %d child entity changed from %s to %s", 
                         self.zone_id, old_child_entity_id, new_child_entity_id)
            
            # Force immediate state update when child entity changes
            self.async_write_ha_state()
        
        # Always update supported features in case child entity features changed
        self._update_supported_features()
        
        # Force state update if child entity mapping changed
        if new_child_entity_id != getattr(self, '_last_child_entity_id', None):
            _LOGGER.debug("Zone %d forcing state update: last=%s, new=%s", 
                         self.zone_id, getattr(self, '_last_child_entity_id', None), new_child_entity_id)
            self.async_write_ha_state()
            self._last_child_entity_id = new_child_entity_id
        
        super()._async_coordinator_updated()
    
    def _update_child_entity_listener(self):
        """Update the listener for child entity state changes."""
        # Remove existing listener
        if hasattr(self, "_child_entity_listener") and self._child_entity_listener:
            self._child_entity_listener()
            self._child_entity_listener = None
        
        # Add new listener if we have a child entity
        if self._current_child_entity_id:
            self._child_entity_listener = self.hass.bus.async_listen(
                "state_changed", self._child_entity_changed
            )
    
    async def async_join_players(self, group_members: list[str]) -> None:
        """Join players together in a group."""
        child_entity_id = self._get_child_entity_id()
        if not child_entity_id:
            return
        
        # Get child entities for all zones in the group
        child_entities = set()
        for member in group_members:
            # Find zone for this member
            if member == self.entity_id:
                child_entities.add(child_entity_id)
            else:
                # Find other zone entities in our coordinator 
                for entity in self.coordinator._entities:
                    if hasattr(entity, 'entity_id') and entity.entity_id == member:
                        member_child = entity._get_child_entity_id()
                        if member_child:
                            child_entities.add(member_child)
        
        # Join child entities if we have any
        child_entities = list(child_entities)
        if len(child_entities) > 1:
            await self.hass.services.async_call(
                "media_player", "join", {
                    "entity_id": child_entities[0],
                    "group_members": child_entities
                }
            )
        elif child_entity_id:
            # Single child - ensure it's grouped with itself
            await self.hass.services.async_call(
                "media_player", "join", {
                    "entity_id": child_entity_id,
                    "group_members": [child_entity_id]
                }
            )
    
    async def async_unjoin_player(self) -> None:
        """Remove this player from any group."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id:
            # Check if other zones are still using this child entity
            other_zones_using_child = []
            for entity in self.coordinator._entities:
                if (hasattr(entity, '_get_child_entity_id') and 
                    entity != self and 
                    entity._get_child_entity_id() == child_entity_id):
                    other_zones_using_child.append(entity.entity_id)
            
            # Only unjoin the child if no other zones are using it
            if not other_zones_using_child:
                await self.hass.services.async_call(
                    "media_player", "unjoin", {"entity_id": child_entity_id}
                )
    
    @property
    def group_members(self) -> list[str] | None:
        """Return the group members if this entity is in a group."""
        child_entity = self._get_child_entity()
        if not child_entity:
            return None
        
        child_group_members = child_entity.attributes.get("group_members", [])
        if not child_group_members:
            return None
        
        # Map child group members back to zone entities
        zone_members = []
        for entity in self.coordinator._entities:
            if (hasattr(entity, '_get_child_entity_id') and 
                entity._get_child_entity_id() in child_group_members):
                zone_members.append(entity.entity_id)
        
        return zone_members if zone_members else None
