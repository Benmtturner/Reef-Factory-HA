"""Shared entity base for the KH Keeper."""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import KhCoordinator


class KhEntity(CoordinatorEntity[KhCoordinator]):
    """Base entity bound to the KH coordinator."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KhCoordinator, key: str) -> None:
        super().__init__(coordinator)
        identifier = coordinator.serial or coordinator.host
        self._attr_unique_id = f"{identifier}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            connections=(
                {(CONNECTION_NETWORK_MAC, coordinator.mac)} if coordinator.mac else set()
            ),
            name=coordinator.entry.title,
            manufacturer=MANUFACTURER,
            model=coordinator.model,
            serial_number=coordinator.serial,
            sw_version=coordinator.firmware,
            configuration_url=f"http://{coordinator.host}/",
        )
