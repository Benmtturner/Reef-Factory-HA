"""Entity bases for the Red Sea (ReefBeat) family.

One HA device per physical ReefDose; its dosing heads are entities named
"Head N …". Identity is the device's ``hwid`` (a stable MAC — Red Sea addresses
don't roll like EcoTech's).
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import (
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
    format_mac,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .api import HeadState
from .const import MANUFACTURER
from .coordinator import RedSeaDoserCoordinator


def doser_device_info(coordinator: RedSeaDoserCoordinator) -> DeviceInfo:
    """The ReefDose as a single HA device."""
    connections: set[tuple[str, str]] = set()
    if coordinator.hwid:
        connections = {(CONNECTION_NETWORK_MAC, format_mac(coordinator.hwid))}
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.hwid or coordinator.host)},
        connections=connections,
        name=coordinator.entry.title,
        manufacturer=MANUFACTURER,
        model=coordinator.model_name,
        sw_version=coordinator.firmware,
        configuration_url=f"http://{coordinator.host}/",
    )


class RedSeaDoserEntity(CoordinatorEntity[RedSeaDoserCoordinator]):
    """Base for a device-level ReefDose entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RedSeaDoserCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.hwid or coordinator.host}_{key}"
        self._attr_device_info = doser_device_info(coordinator)


class RedSeaHeadEntity(RedSeaDoserEntity):
    """Base for a per-head ReefDose entity (name prefixed 'Head N')."""

    def __init__(
        self, coordinator: RedSeaDoserCoordinator, head: int, key: str, name: str
    ) -> None:
        super().__init__(coordinator, f"head{head}_{key}")
        self._head = head
        self._attr_name = f"Head {head} {name}"

    @property
    def _head_state(self) -> HeadState | None:
        state = self.coordinator.data
        return state.heads.get(self._head) if state else None

    @property
    def available(self) -> bool:
        return bool(super().available and self._head_state is not None)
