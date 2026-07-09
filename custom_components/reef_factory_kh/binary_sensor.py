"""Binary sensor platform for Reef Factory devices (KH Keeper + doser)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .const import FAMILY_DP
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for whichever device family this entry is."""
    coordinator = entry.runtime_data

    if coordinator.family == FAMILY_DP:
        async_add_entities([DpDosing(coordinator)])
        return

    async_add_entities(
        [
            KhReagentAlert(coordinator),
            KhOutOfRange(coordinator),
        ]
    )


class KhReagentAlert(KhEntity, BinarySensorEntity):
    """Reagent alert flag reported by the device."""

    _attr_name = "Reagent Alert"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:flask-empty-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reagent_alert")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.reagent_alert if self.coordinator.data else None


class KhOutOfRange(KhEntity, BinarySensorEntity):
    """On when the latest KH is outside the configured alert band."""

    _attr_name = "KH Out of Range"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "kh_out_of_range")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.kh_out_of_range if self.coordinator.data else None


class DpDosing(KhEntity, BinarySensorEntity):
    """True while the doser pump is dispensing."""

    _attr_name = "Dosing"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dosing")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.dosing if self.coordinator.data else None
