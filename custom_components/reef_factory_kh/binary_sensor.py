"""Binary sensor platform for Reef Factory devices (KH Keeper + doser)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
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
        # Parameterised doser actions, registered on this one-per-device entity.
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            "manual_refill",
            {
                vol.Required("amount"): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional("days", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            },
            "async_service_manual_refill",
        )
        platform.async_register_entity_service(
            "skip_next",
            {vol.Required("percent"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))},
            "async_service_skip_next",
        )
        platform.async_register_entity_service(
            "submit_calibration",
            {
                vol.Required("measured_ml"): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional("period", default=3): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
            },
            "async_service_submit_calibration",
        )
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

    # Entity-service handlers (registered in async_setup_entry).
    async def async_service_manual_refill(self, amount: float, days: int = 0) -> None:
        await self.coordinator.async_dp_manual_refill(amount, days)

    async def async_service_skip_next(self, percent: int) -> None:
        await self.coordinator.async_dp_skip_next(percent)

    async def async_service_submit_calibration(
        self, measured_ml: float, period: int = 3
    ) -> None:
        await self.coordinator.async_dp_calibration_submit(measured_ml, period)
