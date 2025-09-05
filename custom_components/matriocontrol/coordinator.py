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

UPDATE_INTERVAL = timedelta(seconds=30)


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
            if not self.controller.socket:
                _LOGGER.debug("No socket connection, attempting to connect")
                # Run connection in executor to avoid blocking event loop
                connected = await self.hass.async_add_executor_job(self.controller.connect)
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
            
            # Query device information to check connectivity
            device_info = {}
            names = {}
            heartbeat_received = False
            zone_states = {}
            
            # Retry ALLNAMES command up to 2 times
            for attempt in range(2):
                try:
                    # Try to get device info (this will test connectivity)
                    device_info = await self.hass.async_add_executor_job(self.controller.query_device_info)
                    
                    # Get zone and input names - this is critical
                    names = await self.hass.async_add_executor_job(self.controller.query_all_names)
                    
                    # Update the controller's input mappings with actual device names
                    if names:
                        for i in range(1, 9):
                            input_key = f"input_{i}"
                            if input_key in names:
                                self.controller.inputs[i] = names[input_key]
                    
                    heartbeat_received = True
                    break  # Success, exit retry loop
                    
                except (ConnectionError, RuntimeError, NotImplementedError) as e:
                    _LOGGER.warning("Attempt %d failed to query device info: %s", attempt + 1, e)
                    if attempt == 1:  # Last attempt failed
                        _LOGGER.error("ALLNAMES command failed after 2 attempts - integration cannot function without zone names")
                        raise UpdateFailed("Device did not respond to ALLNAMES command after 2 attempts")
                    
                    # Try to reconnect before retry
                    await self.hass.async_add_executor_job(self.controller.disconnect)
                    connected = await self.hass.async_add_executor_job(self.controller.connect)
                    if not connected:
                        _LOGGER.error("Failed to reconnect to device on attempt %d", attempt + 1)
                        raise UpdateFailed("Failed to reconnect to device")
            
            # Get current zone states using HNG sync
            try:
                _LOGGER.debug("Getting zone states via HNG sync...")
                # Pass input mappings to the controller for proper input name decoding
                input_mappings = self.controller.get_available_inputs()
                zone_states = await self.hass.async_add_executor_job(self.controller.get_zone_states, input_mappings)
                _LOGGER.debug("HNG sync returned %d zones", len(zone_states))
            except Exception as e:
                _LOGGER.warning("HNG sync failed: %s", e)
                zone_states = {}
            
            result = {
                "connected": True,
                "zones": {f"zone_{i}": names.get(f"zone_{i-1}", f"Zone {i}") for i in range(1, 9)},
                "inputs": self.controller.get_available_inputs(),
                "device_info": device_info,
                "names": names,
                "last_heartbeat": heartbeat_received,
                "input_mappings": {i: names.get(f"input_{i}", f"Input{i}") for i in range(1, 9)},
                "zone_names": {i: names.get(f"zone_{i-1}", f"Zone {i}") for i in range(1, 9)},
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