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
        try:
            # Check if we need to connect
            if not self.controller.socket:
                if not self.controller.connect():
                    return {
                        "connected": False,
                        "zones": {},
                        "inputs": self.controller.get_available_inputs(),
                        "device_info": {},
                        "last_heartbeat": None,
                    }
            
            # Query device information to check connectivity
            device_info = {}
            names = {}
            heartbeat_received = False
            
            try:
                # Try to get device info (this will test connectivity)
                device_info = self.controller.query_device_info()
                
                # Get zone and input names
                names = self.controller.query_all_names()
                
                # Update the controller's input mappings with actual device names
                if names:
                    for i in range(1, 9):
                        input_key = f"input_{i}"
                        if input_key in names:
                            self.controller.inputs[i] = names[input_key]
                
                heartbeat_received = True
            except (ConnectionError, RuntimeError, NotImplementedError) as e:
                _LOGGER.warning("Failed to query device info: %s", e)
                # If query fails, try to reconnect
                self.controller.disconnect()
                if not self.controller.connect():
                    return {
                        "connected": False,
                        "zones": {},
                        "inputs": self.controller.get_available_inputs(),
                        "device_info": device_info,
                        "names": names,
                        "last_heartbeat": None,
                    }
                # After reconnection, try heartbeat check instead
                heartbeat_received = self.controller.check_heartbeat()
            
            return {
                "connected": True,
                "zones": {f"zone_{i}": names.get(f"zone_{i-1}", f"Zone {i}") for i in range(1, 9)},
                "inputs": self.controller.get_available_inputs(),
                "device_info": device_info,
                "names": names,
                "last_heartbeat": heartbeat_received,
            }
            
        except Exception as err:
            _LOGGER.error("Error communicating with Matrio device: %s", err)
            return {
                "connected": False,
                "zones": {},
                "inputs": self.controller.get_available_inputs(),
                "device_info": {},
                "names": {},
                "last_heartbeat": None,
            }