"""Media player platform for Matrio Control."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaPlayerDeviceClass,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event, State
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, INPUTS, VOLUME_MAX, POWER_OFF, MUTE_STATE_MUTED
from .coordinator import MatrioControlDataUpdateCoordinator
from .entity import MatrioControlEntity

_LOGGER = logging.getLogger(__name__)

# Coordinator data keys
CHILD_ENTITY_MAPPINGS_KEY = "child_entity_mappings"
ZONE_STATES_KEY = "zone_states"
INPUT_MAPPINGS_KEY = "input_mappings"
CONNECTED_KEY = "connected"


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
            | MediaPlayerEntityFeature.PLAY_MEDIA
        )
        
        self._base_features = base_features
        self._attr_supported_features = self._base_features
        
        # Initialize child entity tracking (deferred until hass is available)
        self._current_child_entity_id = None
        
        # Initialize state change tracking attributes
        self._child_entity_unsubscribers = []  # Unsubscribe functions for child entity state change listeners
        self._ha_started_listener = None  # Listener for homeassistant_started event
    
    def _get_child_entity_id(self) -> str | None:
        """Get the current child entity ID based on selected input."""
        child_entity_mappings = self.coordinator.data.get(CHILD_ENTITY_MAPPINGS_KEY, {})
        
        if not child_entity_mappings:
            return None
        
        # Get current zone input
        zone_states = self.coordinator.data.get(ZONE_STATES_KEY, {})
        zone_state = zone_states.get(self.zone_id)
        
        if not zone_state:
            return None
            
        # Get input number from zone state
        current_input = zone_state.get("input_number")
        
        if current_input is None:
            return None
        
        # Convert to input_N format to match configuration
        input_key = f"input_{current_input}"
        result = child_entity_mappings.get(input_key)
        
        return result


    def _get_zone_state(self) -> dict | None:
        """Get zone state from coordinator data."""
        zone_states = self.coordinator.data.get(ZONE_STATES_KEY, {})
        return zone_states.get(self.zone_id)

    def _get_child_entity(self) -> State | None:
        """Get the child media player entity object."""
        child_entity_id = self._get_child_entity_id()
        if child_entity_id and self.hass:
            return self.hass.states.get(child_entity_id)
        return None

    def _get_child_attribute(self, attr_name: str) -> Any:
        """Get an attribute from the child entity if available."""
        child_entity = self._get_child_entity()
        if child_entity:
            return child_entity.attributes.get(attr_name)
        return None

    @property
    def _is_connected(self) -> bool:
        """Check if the device is connected."""
        return self.coordinator.data.get(CONNECTED_KEY, False)

    def _update_supported_features(self):
        """Update supported features based on child entity capabilities."""
        # Don't try to access child entities before hass is available
        if not self.hass:
            return
            
        child_entity = self._get_child_entity()
        child_entity_id = self._current_child_entity_id
        
        _LOGGER.debug("Zone %d _update_supported_features: child_entity_id=%s, child_entity=%s", 
                     self.zone_id, child_entity_id, child_entity is not None)
        
        if child_entity and child_entity.state != "unavailable":
            # Get child entity's actual supported features
            child_features = child_entity.attributes.get("supported_features", 0)
            
            # Combine base receiver features with child's media playback features
            # Filter child features to only include ones that make sense to pass through
            allowed_child_features = (
                MediaPlayerEntityFeature.PAUSE |
                MediaPlayerEntityFeature.PLAY |
                MediaPlayerEntityFeature.STOP |
                MediaPlayerEntityFeature.PREVIOUS_TRACK |
                MediaPlayerEntityFeature.NEXT_TRACK |
                MediaPlayerEntityFeature.SEEK |
                MediaPlayerEntityFeature.REPEAT_SET |
                MediaPlayerEntityFeature.SHUFFLE_SET |
                MediaPlayerEntityFeature.CLEAR_PLAYLIST |
                MediaPlayerEntityFeature.PLAY_MEDIA
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
    
    def _handle_auto_power_management(self, changed_entity_id: str, old_state: State | None, new_state: State | None) -> None:
        """Handle auto-power management when mapped child entity starts playing."""
        if not (old_state and new_state):
            return
            
        old_child_state = old_state.state
        new_child_state = new_state.state
        
        # Auto power management: turn zone on when its currently mapped child starts playing
        if old_child_state != "playing" and new_child_state == "playing":
            zone_state = self._get_zone_state()
            if zone_state and zone_state.get("power") == POWER_OFF:
                # Check if this child entity matches the zone's current input mapping
                current_child_entity_id = self._get_child_entity_id()
                if changed_entity_id == current_child_entity_id:
                    _LOGGER.info("Zone %d auto-powering on: child entity %s started playing", 
                               self.zone_id, changed_entity_id)
                    # Only power on - input selection is already correct
                    self.hass.async_create_task(self.async_turn_on())

    def _handle_child_feature_updates(self, old_state: State | None, new_state: State | None) -> bool:
        """Handle child entity feature changes and availability changes.
        
        Returns True if state update was handled internally, False if caller should update.
        """
        if not (old_state and new_state):
            return False
            
        old_features = old_state.attributes.get("supported_features", 0)
        new_features = new_state.attributes.get("supported_features", 0)
        old_available = old_state.state != "unavailable"
        new_available = new_state.state != "unavailable"
        
        if old_features != new_features or old_available != new_available:
            # Child entity supported features changed or availability changed - update our features
            self._force_child_entity_resolution()
            return True  # _force_child_entity_resolution calls async_write_ha_state if needed
            
        return False

    @callback
    def _child_entity_changed(self, event: Event) -> None:
        """Handle child entity state changes."""
        changed_entity_id = event.data["entity_id"]
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        
        # Get all mapped child entities for this zone
        child_entity_mappings = self.coordinator.data.get(CHILD_ENTITY_MAPPINGS_KEY, {})
        mapped_child_entities = list(child_entity_mappings.values())
        
        # Handle auto-power management for mapped child entities
        if changed_entity_id in mapped_child_entities:
            self._handle_auto_power_management(changed_entity_id, old_state, new_state)
        
        # Handle feature updates for currently active child entity
        if changed_entity_id == self._current_child_entity_id:
            _LOGGER.debug("Zone %d current child entity %s state changed", 
                         self.zone_id, self._current_child_entity_id)
            
            if not self._handle_child_feature_updates(old_state, new_state):
                self.async_write_ha_state()

    def _force_child_entity_resolution(self):
        """Force immediate child entity resolution and feature update."""
        if not self._current_child_entity_id:
            return
            
        old_features = self._attr_supported_features
        child_entity = self._get_child_entity()
        
        if child_entity:
            _LOGGER.info("Zone %d resolved child entity %s: state=%s, features=0x%x", 
                       self.zone_id, self._current_child_entity_id, child_entity.state,
                       child_entity.attributes.get("supported_features", 0))
        else:
            _LOGGER.debug("Zone %d force resolution: no child entity found for id=%s", 
                         self.zone_id, self._current_child_entity_id)
            
        self._update_supported_features()
        
        if old_features != self._attr_supported_features:
            _LOGGER.info("Zone %d features changed: 0x%x -> 0x%x", 
                       self.zone_id, old_features, self._attr_supported_features)
            self.async_write_ha_state()
    
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        zones = self.coordinator.data.get("zones", {})
        zone_key = f"zone_{self.zone_id}"
        zone_name = zones.get(zone_key, f"Zone {self.zone_id}")
        _LOGGER.debug("Zone %d name lookup: zones=%s, key=%s, result=%s", 
                     self.zone_id, zones, zone_key, zone_name)
        return zone_name

    @property
    def state(self) -> MediaPlayerState:
        """Return the state of the device."""
        if not self._is_connected:
            return MediaPlayerState.OFF
        
        zone_state = self._get_zone_state()
        
        # If zone is off, return OFF regardless of child state
        if zone_state and zone_state.get("power") == POWER_OFF:
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
        return self._get_child_attribute("media_content_id")
    
    @property
    def media_content_type(self) -> str | None:
        """Return the content type of current playing media."""
        return self._get_child_attribute("media_content_type")
    
    @property
    def media_duration(self) -> int | None:
        """Return the duration of current playing media in seconds."""
        return self._get_child_attribute("media_duration")
    
    @property
    def media_position(self) -> int | None:
        """Return the position of current playing media in seconds."""
        return self._get_child_attribute("media_position")
    
    @property
    def media_position_updated_at(self) -> datetime | None:
        """Return the time media position was last updated."""
        return self._get_child_attribute("media_position_updated_at")
    
    @property
    def media_image_url(self) -> str | None:
        """Return the image URL of current playing media."""
        return self._get_child_attribute("entity_picture")
    
    @property
    def media_image_remotely_accessible(self) -> bool:
        """Return if the image is remotely accessible."""
        return self._get_child_attribute("media_image_remotely_accessible") or False
    
    @property
    def media_title(self) -> str | None:
        """Return the title of current playing media."""
        return self._get_child_attribute("media_title")
    
    @property
    def media_artist(self) -> str | None:
        """Return the artist of current playing media."""
        return self._get_child_attribute("media_artist")
    
    @property
    def media_album_name(self) -> str | None:
        """Return the album name of current playing media."""
        return self._get_child_attribute("media_album_name")
    
    @property
    def media_album_artist(self) -> str | None:
        """Return the album artist of current playing media."""
        return self._get_child_attribute("media_album_artist")
    
    @property
    def media_track(self) -> int | None:
        """Return the track number of current playing media."""
        return self._get_child_attribute("media_track")
    
    @property
    def media_series_title(self) -> str | None:
        """Return the series title of current playing media."""
        return self._get_child_attribute("media_series_title")
    
    @property
    def media_season(self) -> str | None:
        """Return the season of current playing media."""
        return self._get_child_attribute("media_season")
    
    @property
    def media_episode(self) -> str | None:
        """Return the episode of current playing media."""
        return self._get_child_attribute("media_episode")
    
    @property
    def media_channel(self) -> str | None:
        """Return the channel of current playing media."""
        return self._get_child_attribute("media_channel")
    
    @property
    def media_playlist(self) -> str | None:
        """Return the playlist of current playing media."""
        return self._get_child_attribute("media_playlist")

    @property
    def shuffle(self) -> bool | None:
        """Return the shuffle state."""
        return self._get_child_attribute("shuffle")
    
    @property
    def repeat(self) -> str | None:
        """Return the repeat mode."""
        return self._get_child_attribute("repeat")

    @property
    def source_list(self) -> list[str]:
        """Return the list of available input sources."""
        # Use input_mappings if available, otherwise fall back to inputs
        input_mappings = self.coordinator.data.get(INPUT_MAPPINGS_KEY, {})
        if input_mappings:
            return list(input_mappings.values())
        
        inputs = self.coordinator.data.get("inputs", INPUTS)
        return list(inputs.values())

    @property
    def source(self) -> str | None:
        """Return the current input source."""
        if not self._is_connected:
            return None
            
        zone_state = self._get_zone_state()
        
        if zone_state and "input" in zone_state:
            return zone_state["input"]
        
        return None

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if not self._is_connected:
            return None
            
        zone_state = self._get_zone_state()
        
        if zone_state and "volume" in zone_state:
            # Convert from 0..38 range to 0..1 range
            volume = zone_state["volume"]
            return volume / VOLUME_MAX if VOLUME_MAX > 0 else 0.0
        
        return None

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        if not self._is_connected:
            return None
            
        # Get zone state from HNG sync data
        zone_states = self.coordinator.data.get(ZONE_STATES_KEY, {})
        zone_state = zone_states.get(self.zone_id)
        
        if zone_state and "mute" in zone_state:
            return zone_state["mute"] == MUTE_STATE_MUTED
        
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

    def _find_input_id_by_name(self, source: str) -> int | None:
        """Find input ID by source name using mappings or fallback inputs."""
        # Try input_mappings first (device names)
        input_mappings = self.coordinator.data.get(INPUT_MAPPINGS_KEY, {})
        if input_mappings:
            for input_id, name in input_mappings.items():
                if name == source:
                    return input_id
        
        # Fall back to default inputs
        inputs = self.coordinator.data.get("inputs", INPUTS)
        for input_id, name in inputs.items():
            if name == source:
                return input_id
        
        return None

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        input_id = self._find_input_id_by_name(source)
        
        if input_id:
            _LOGGER.debug("Zone %d selecting input %s for source '%s'", self.zone_id, input_id, source)
            await self.coordinator.controller.set_input(self.zone_id, input_id)
            # State will be updated via broadcast callback
        else:
            _LOGGER.warning("Zone %d: no input found for source '%s'", self.zone_id, source)

    async def _delegate_to_child(self, service_name: str, action_description: str, **service_data) -> bool:
        """Delegate a service call to the child entity with common error handling.
        
        Args:
            service_name: The media_player service to call (e.g., 'media_play', 'shuffle_set')
            action_description: Human-readable description for logging (e.g., 'play', 'set shuffle')
            **service_data: Additional service data (merged with entity_id)
            
        Returns:
            True if the service was called successfully, False if no child entity or error occurred.
        """
        child_entity_id = self._get_child_entity_id()
        if not child_entity_id:
            return False
            
        try:
            service_data["entity_id"] = child_entity_id
            await self.hass.services.async_call("media_player", service_name, service_data)
            return True
        except HomeAssistantError as err:
            _LOGGER.warning("Zone %d failed to %s on child entity %s: %s", 
                          self.zone_id, action_description, child_entity_id, err)
            return False

    async def async_media_play(self) -> None:
        """Send play command to child entity."""
        await self._delegate_to_child("media_play", "play")
    
    async def async_media_pause(self) -> None:
        """Send pause command to child entity."""
        await self._delegate_to_child("media_pause", "pause")
    
    async def async_media_stop(self) -> None:
        """Send stop command to child entity."""
        await self._delegate_to_child("media_stop", "stop")
    
    async def async_media_previous_track(self) -> None:
        """Send previous track command to child entity."""
        await self._delegate_to_child("media_previous_track", "skip to previous track")
    
    async def async_media_next_track(self) -> None:
        """Send next track command to child entity."""
        await self._delegate_to_child("media_next_track", "skip to next track")
    
    async def async_media_seek(self, position: float) -> None:
        """Send seek command to child entity."""
        await self._delegate_to_child("media_seek", "seek", seek_position=position)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode on child entity."""
        await self._delegate_to_child("shuffle_set", "set shuffle", shuffle=shuffle)

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode on child entity."""
        await self._delegate_to_child("repeat_set", "set repeat", repeat=repeat)
    
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media via child entity."""
        success = await self._delegate_to_child(
            "play_media", 
            "play media",
            media_content_type=media_type,
            media_content_id=media_id,
            **kwargs
        )
        if not success and not self._get_child_entity_id():
            # No child entity mapped - cannot play media
            # This maintains Music Assistant compatibility while providing clear feedback
            _LOGGER.warning("Zone %d cannot play media: no child entity mapped to current input", 
                          self.zone_id)
    
    async def async_added_to_hass(self) -> None:
        """Called when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Initialize child entity tracking now that hass is available
        self._current_child_entity_id = self._get_child_entity_id()
        
        # Set up listener for child entity changes
        self._update_child_entity_listener()
        
        # Update supported features based on current child entity
        self._update_supported_features()
        
        # Listen for homeassistant_started event to update features after all integrations load
        @callback
        def on_homeassistant_started(event):
            """Handle homeassistant_started event to update features after all integrations load."""
            if self._current_child_entity_id:
                old_features = self._attr_supported_features
                self._update_supported_features()
                if old_features != self._attr_supported_features:
                    _LOGGER.info("Zone %d feature update on HA started: 0x%x -> 0x%x (child entity %s now available)", 
                               self.zone_id, old_features, self._attr_supported_features, self._current_child_entity_id)
                    self.async_write_ha_state()
        
        # Listen for homeassistant_started event (remove listener on entity removal)
        self._ha_started_listener = self.hass.bus.async_listen_once("homeassistant_started", on_homeassistant_started)
        
        # The targeted state change listeners in _update_child_entity_listener()
        # handle all the child entity state changes we need
        

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from hass."""
        # Clean up child entity state change listeners
        for unsub in self._child_entity_unsubscribers:
            unsub()
        self._child_entity_unsubscribers.clear()
        
        # Clean up homeassistant_started event listener if it exists
        if self._ha_started_listener:
            self._ha_started_listener()
        
        await super().async_will_remove_from_hass()
    
    @callback
    def _async_coordinator_updated(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if child entity mapping changed
        new_child_entity_id = self._get_child_entity_id()
        old_child_entity_id = self._current_child_entity_id
        
        if new_child_entity_id != old_child_entity_id:
            # Update cached child entity ID
            self._current_child_entity_id = new_child_entity_id
            
            # Update state tracking for the new child entity
            self._update_child_entity_listener()
            
            _LOGGER.info("Zone %d child entity changed from %s to %s", 
                         self.zone_id, old_child_entity_id, new_child_entity_id)
            
            # Force immediate state update when child entity changes
            self.async_write_ha_state()
        
        # Update supported features (always needed as features might change)
        self._update_supported_features()
        
        super()._async_coordinator_updated()
    
    def _update_child_entity_listener(self):
        """Update the listener for child entity state changes."""
        if not self.hass:
            # Remove existing listeners if no hass context
            for unsub in self._child_entity_unsubscribers:
                unsub()
            self._child_entity_unsubscribers.clear()
            return
            
        # Get all mapped child entities for this zone (for auto-power management)
        child_entity_mappings = self.coordinator.data.get(CHILD_ENTITY_MAPPINGS_KEY, {})
        entities_to_track = set()
        
        # Add all mapped child entities (for auto-power when any mapped child starts playing)
        for child_entity_id in child_entity_mappings.values():
            if child_entity_id:
                entities_to_track.add(child_entity_id)
        
        # Add current child entity (for feature updates and state changes)
        if self._current_child_entity_id:
            entities_to_track.add(self._current_child_entity_id)
        
        # Set up new listeners first, then atomically swap to prevent coverage gaps
        new_unsubscribers = []
        old_unsubscribers = self._child_entity_unsubscribers
        
        try:
            for entity_id in entities_to_track:
                unsub = async_track_state_change_event(
                    self.hass, entity_id, self._child_entity_changed
                )
                new_unsubscribers.append(unsub)
            
            # Atomically replace old listeners with new ones (only if all new listeners succeeded)
            self._child_entity_unsubscribers = new_unsubscribers
            
        except Exception as e:
            # If setting up new listeners failed, clean up any partial listeners we created
            _LOGGER.warning("Failed to set up child entity listeners for zone %d: %s", self.zone_id, e)
            for unsub in new_unsubscribers:
                try:
                    unsub()
                except Exception:
                    pass  # Ignore cleanup errors
            # Keep old listeners active since new setup failed
            return
        
        # Clean up old listeners only after new ones are successfully active
        for unsub in old_unsubscribers:
            try:
                unsub()
            except Exception:
                pass  # Ignore cleanup errors for old listeners
    

