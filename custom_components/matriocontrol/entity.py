"""Base entity for Matrio Control."""
from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_MANUFACTURER, DEVICE_MODEL, DOMAIN
from .coordinator import MatrioControlDataUpdateCoordinator


class MatrioControlEntity(CoordinatorEntity[MatrioControlDataUpdateCoordinator]):
    """Base entity for Matrio Control."""

    def __init__(
        self, 
        coordinator: MatrioControlDataUpdateCoordinator, 
        zone_id: int
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.zone_id = zone_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.data.get("name", "Matrio Control"),
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )
