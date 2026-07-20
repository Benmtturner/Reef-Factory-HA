"""Entity bases for the EcoTech (Mobius) family.

Two device tiers show up in HA: the **bridge** (a hub device) and each **Mobius
device** behind it, linked with ``via_device`` so the UI nests them under the hub.
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .bridge import BridgeDevice
from .const import MANUFACTURER
from .coordinator import DeviceRecord, EcoTechCoordinator


def bridge_identifier(host: str) -> tuple[str, str]:
    return (DOMAIN, f"bridge_{host}")


def bridge_device_info(coordinator: EcoTechCoordinator) -> DeviceInfo:
    """The bridge itself as a HA hub device."""
    info = coordinator.bridge_info or {}
    fw = info.get("fw")
    return DeviceInfo(
        identifiers={bridge_identifier(coordinator.host)},
        name="Multi Reef Bridge",
        manufacturer="Multi Reef",
        model="ESP32 Mobius bridge",
        sw_version=str(fw) if fw else None,
        configuration_url=f"http://{coordinator.host}/",
    )


class EcoTechBridgeEntity(CoordinatorEntity[EcoTechCoordinator]):
    """An entity describing the bridge hub (diagnostics)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EcoTechCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"bridge_{coordinator.host}_{key}"
        self._attr_device_info = bridge_device_info(coordinator)


class EcoTechDeviceEntity(CoordinatorEntity[EcoTechCoordinator]):
    """Base for an entity of one Mobius device behind the bridge."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: EcoTechCoordinator, device: BridgeDevice, key: str
    ) -> None:
        super().__init__(coordinator)
        self._identity = device.identity
        self._attr_unique_id = f"{device.identity}_{key}"
        label = (device.serial or device.mac.replace(":", ""))[-4:]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.identity)},
            name=f"{device.model} {label}",
            manufacturer=MANUFACTURER,
            model=device.model,
            serial_number=device.serial or None,
            via_device=bridge_identifier(coordinator.host),
        )

    @property
    def _record(self) -> DeviceRecord | None:
        return self.coordinator.record(self._identity)

    @property
    def _state(self):
        rec = self._record
        return rec.state if rec else None

    @property
    def available(self) -> bool:
        state = self._state
        return bool(super().available and state is not None and state.ok)
