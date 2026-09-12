"""Data update coordinator for Matrio Control."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .matrio_controller import MatrioController

_LOGGER = logging.getLogger(__name__)

# Stable per-entry ID so repeated failures update the same notification
# instead of stacking up duplicates, and so it can be dismissed on recovery.
_UNREACHABLE_NOTIFICATION_ID = "matriocontrol_unreachable_{entry_id}"

# Broadcasts drive near-real-time updates the rest of the time; this interval
# is also used to throttle an active zone-status resync request (see
# _async_update_data) that catches device-initiated state changes (e.g. a
# firmware auto-timeout) the amp doesn't happen to broadcast on its own.
UPDATE_INTERVAL = timedelta(seconds=20)

# Used instead of UPDATE_INTERVAL to throttle the *next* sync attempt when
# the previous one failed (see has_pending_sync_failure) - retries sooner so
# the controller's required consecutive-failure count is reached in a couple
# of short retries instead of a full UPDATE_INTERVAL between each one, while
# still requiring the same number of consecutive failures to avoid flagging
# a single transient blip as unreachable.
RETRY_INTERVAL = timedelta(seconds=5)


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
        # -inf so the very first eligible tick always fires a sync request,
        # regardless of how long the process/system has been up.
        self._last_sync_request_monotonic = float("-inf")
        self._unreachable_notified = False

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
                    raise UpdateFailed(
                        f"Could not connect to Matrio device at "
                        f"{self.entry.data['host']}:{self.entry.data['port']}"
                    )
                _LOGGER.debug("Connection successful")

            # Actively request a fresh full zone-status resync, throttled to
            # once per UPDATE_INTERVAL. This is what catches device-initiated
            # state changes (e.g. a firmware auto-timeout powering off a
            # zone) that the amp doesn't happen to broadcast on its own -
            # without this, _async_update_data would just keep re-serving a
            # stale cache. Throttled independently of the coordinator's own
            # scheduling because state_callback below also triggers
            # async_request_refresh() on every broadcast, which would
            # otherwise call this far more often than once per interval.
            now = time.monotonic()
            throttle = (
                RETRY_INTERVAL if self.controller.has_pending_sync_failure else UPDATE_INTERVAL
            )
            if now - self._last_sync_request_monotonic >= throttle.total_seconds():
                # Throttle by attempt, not by success. Broadcasts trigger a
                # refresh each, so advancing this only on success would let a
                # failed sync retry immediately - collapsing the
                # SYNC_FAILURE_THRESHOLD window down to back-to-back retries.
                self._last_sync_request_monotonic = now
                sync_succeeded = await self.controller.request_zone_sync()
                if not sync_succeeded and not self.controller.connected:
                    self.update_interval = UPDATE_INTERVAL
                    raise UpdateFailed("Connection lost while refreshing zone state")

                # Also drive the coordinator's own poll cadence, not just this
                # request's internal throttle above - otherwise a failed sync
                # still waits a full UPDATE_INTERVAL before the coordinator
                # even calls in again, and the shorter RETRY_INTERVAL above
                # never has a chance to matter.
                self.update_interval = (
                    RETRY_INTERVAL if self.controller.has_pending_sync_failure else UPDATE_INTERVAL
                )

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
            self._dismiss_unreachable_notification()
            return result

        except UpdateFailed as err:
            # Already the right type - let HA mark entities unavailable.
            self._notify_unreachable(str(err))
            raise
        except Exception as err:
            _LOGGER.debug("Coordinator update failed with error: %s", err)
            # Raise UpdateFailed so HA marks entities unavailable instead of
            # serving an empty/stale dict as if it were fresh, valid data.
            self._notify_unreachable(str(err))
            raise UpdateFailed(f"Error communicating with Matrio device: {err}") from err

    def _notify_unreachable(self, reason: str) -> None:
        """Create a persistent notification the first time this entry's
        device is confirmed unreachable (not on every failed poll)."""
        if self._unreachable_notified:
            return
        self._unreachable_notified = True
        persistent_notification.async_create(
            self.hass,
            f"The Matrio device at {self.entry.data['host']} is unreachable: {reason}. "
            "Zone controls will be unavailable until it reconnects.",
            title="Matrio Control device unreachable",
            notification_id=_UNREACHABLE_NOTIFICATION_ID.format(entry_id=self.entry.entry_id),
        )

    def _dismiss_unreachable_notification(self) -> None:
        """Clear the unreachable notification once the device responds again."""
        if not self._unreachable_notified:
            return
        self._unreachable_notified = False
        persistent_notification.async_dismiss(
            self.hass, _UNREACHABLE_NOTIFICATION_ID.format(entry_id=self.entry.entry_id)
        )
    
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
