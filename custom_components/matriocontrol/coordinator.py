"""Data update coordinator for Matrio Control."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .matrio_controller import MatrioController

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=300)  # Reduced polling - rely on broadcast updates


class MatrioControlDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Matrio device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self.controller = MatrioController(
            entry.data["host"], 
            entry.data["port"]
        )
        
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
                    # Trigger coordinator update when state changes
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
            
            # Get actual zone and input names from controller
            zone_names = getattr(self.controller, 'zone_names', {})
            input_mappings = self.controller.get_available_inputs()
            
            result = {
                "connected": True,
                "zones": {f"zone_{i}": zone_names.get(i, f"Zone {i}") for i in range(1, 9)},
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
