"""Data update coordinator for Matrio Control."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .matrio_controller import MatrioController

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=60)  # Minimal polling - rely on broadcast updates for real-time changes


class MatrioControlDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Matrio device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.controller = MatrioController(
            entry.data["host"], 
            entry.data["port"]
        )
        self._entities = []  # Track entities for direct updates
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self):
        """Update data via library."""
        _LOGGER.debug("Coordinator _async_update_data called")
        try:
            # Check if we need to connect
            if not self.controller.connected:
                _LOGGER.debug("No connection, attempting to connect")
                # Use the new async connect method with state callback
                def state_callback(zones):
                    _LOGGER.debug("State callback received %d zones", len(zones))
                    # Update entities directly for immediate state changes
                    self._update_entities_from_zones(zones)
                    # Also trigger coordinator update for data consistency
                    self.hass.async_create_task(self.async_request_refresh())
                
                connected = await self.controller.connect(state_callback)
                if not connected:
                    _LOGGER.debug("Connection failed")
                    return {
                        "connected": False,
                        "zones": {},
                        "inputs": self.controller.get_available_inputs(),
                        "device_info": {},
                        "last_heartbeat": None,
                        "zone_states": {},
                    }
                _LOGGER.debug("Connection successful")
            
            # Get current zone states from the controller
            zone_states = self.controller.zones.copy()
            _LOGGER.debug("Retrieved %d zones from controller", len(zone_states))
            
            # If we don't have zone states yet, wait for them to be populated
            if not zone_states:
                _LOGGER.debug("Zone states not available yet, waiting for device state...")
                # Wait up to 5 seconds for zone states to be populated
                for _ in range(50):  # 50 * 0.1 = 5 seconds
                    await asyncio.sleep(0.1)
                    zone_states = self.controller.zones.copy()
                    if zone_states:
                        _LOGGER.debug("Zone states now available: %d zones", len(zone_states))
                        break
                else:
                    _LOGGER.warning("Zone states not available after waiting, using empty states")
            
            # Get actual zone and input names from controller
            zone_names = getattr(self.controller, 'zone_names', {})
            input_mappings = self.controller.get_available_inputs()
            
            # If we don't have zone names yet, wait for them to be populated
            if not zone_names:
                _LOGGER.debug("Zone names not available yet, waiting for device initialization...")
                # Wait up to 5 seconds for zone names to be populated
                for _ in range(50):  # 50 * 0.1 = 5 seconds
                    await asyncio.sleep(0.1)
                    zone_names = getattr(self.controller, 'zone_names', {})
                    if zone_names:
                        _LOGGER.debug("Zone names now available: %s", zone_names)
                        break
                else:
                    _LOGGER.warning("Zone names not available after waiting, using defaults")
            
            _LOGGER.debug("Zone names from controller: %s", zone_names)
            _LOGGER.debug("Zone names type: %s", type(zone_names))
            
            # Create zones dictionary with proper names
            zones_dict = {}
            for i in range(1, 9):
                zone_name = zone_names.get(i, f"Zone {i}")
                zones_dict[f"zone_{i}"] = zone_name
                _LOGGER.debug("Zone %d: %s", i, zone_name)
            
            result = {
                "connected": True,
                "zones": zones_dict,
                "inputs": input_mappings,
                "device_info": {},
                "names": {},
                "last_heartbeat": True,
                "input_mappings": input_mappings,
                "zone_names": zone_names,
                "zone_states": zone_states,
            }
            _LOGGER.debug("Coordinator update successful, returning data with %d zone states", len(zone_states))
            _LOGGER.debug("Zone states data: %s", zone_states)
            return result
            
        except Exception as err:
            _LOGGER.debug("Coordinator update failed with error: %s", err)
            _LOGGER.error("Error communicating with Matrio device: %s", err)
            return {
                "connected": False,
                "zones": {},
                "inputs": self.controller.get_available_inputs(),
                "device_info": {},
                "names": {},
                "last_heartbeat": None,
                "zone_states": {},
            }
    
    def register_entity(self, entity):
        """Register an entity for direct state updates."""
        if entity not in self._entities:
            self._entities.append(entity)
            _LOGGER.debug("Registered entity: %s", entity.entity_id)
    
    def unregister_entity(self, entity):
        """Unregister an entity from direct state updates."""
        if entity in self._entities:
            self._entities.remove(entity)
            _LOGGER.debug("Unregistered entity: %s", entity.entity_id)
    
    def _update_entities_from_zones(self, zones):
        """Update all registered entities with new zone data."""
        if not zones:
            return
        
        _LOGGER.debug("Updating %d entities with zone data", len(self._entities))
        
        # Update coordinator data immediately
        current_data = self.data or {}
        current_data["zone_states"] = zones
        self.data = current_data
        
        # Schedule entity updates on the event loop
        for entity in self._entities:
            if hasattr(entity, 'schedule_update_ha_state'):
                # Use schedule_update_ha_state for immediate entity updates
                entity.schedule_update_ha_state()
                _LOGGER.debug("Scheduled update for entity: %s", entity.entity_id)
