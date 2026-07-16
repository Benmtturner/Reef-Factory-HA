"""Binary sensor platform for Reef Factory devices (KH Keeper + doser)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_platform
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
        platform.async_register_entity_service(
            "set_schedule",
            {
                vol.Required("number_of_doses"): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Required("daily_total_ml"): vol.All(vol.Coerce(float), vol.Range(min=0)),
                vol.Optional("days"): vol.All(
                    cv.ensure_list, [vol.In(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])]
                ),
            },
            "async_service_set_schedule",
        )
        platform.async_register_entity_service(
            "set_doses",
            {
                vol.Required("doses"): vol.All(
                    cv.ensure_list,
                    [
                        {
                            vol.Required("time"): cv.time,
                            vol.Required("ml"): vol.All(vol.Coerce(float), vol.Range(min=0)),
                        }
                    ],
                    vol.Length(min=1, max=24),
                ),
                vol.Optional("days"): vol.All(
                    cv.ensure_list, [vol.In(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])]
                ),
            },
            "async_service_set_doses",
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        return {
            "refill_active": bool(state.manual_active),
            "refill_total_ml": state.refill_total_ml,
            "refill_days": state.refill_days,
        }

    # Entity-service handlers (registered in async_setup_entry).
    async def async_service_manual_refill(self, amount: float, days: int = 0) -> None:
        await self.coordinator.async_dp_manual_refill(amount, days)

    async def async_service_skip_next(self, percent: int) -> None:
        await self.coordinator.async_dp_skip_next(percent)

    async def async_service_submit_calibration(
        self, measured_ml: float, period: int = 3
    ) -> None:
        await self.coordinator.async_dp_calibration_submit(measured_ml, period)

    def _resolve_day_mask(self, days: list[str] | None) -> int:
        """Day bitfield (bit0=Sun..bit6=Sat, bit7=enabled) from weekday names, or
        keep the device's current days when none are given."""
        if days:
            bit = {"Sun": 0, "Mon": 1, "Tue": 2, "Wed": 3, "Thu": 4, "Fri": 5, "Sat": 6}
            return 0x80 | sum(1 << bit[d] for d in days)
        state = self.coordinator.data
        return state.day_mask if state and state.day_mask else 0xFF

    async def async_service_set_schedule(
        self, number_of_doses: int, daily_total_ml: float, days: list[str] | None = None
    ) -> None:
        """Write an evenly-spaced schedule of ``number_of_doses`` equal doses that
        sum to ``daily_total_ml``, on the given days (or the current days)."""
        count = number_of_doses
        per_dose = round(daily_total_ml / count, 2) if count else 0.0
        doses = [((i * 1440) // count, per_dose) for i in range(count)]
        await self.coordinator.async_dp_write_doses(doses, self._resolve_day_mask(days))

    async def async_service_set_doses(
        self, doses: list[dict], days: list[str] | None = None
    ) -> None:
        """Write an explicit per-dose schedule — each entry a ``{time, ml}`` — on
        the given days (or the current days). Order does not matter (sorted by
        time here). Powers the card's per-dose grid and adjust-by-%."""
        parsed = sorted(
            (d["time"].hour * 60 + d["time"].minute, round(float(d["ml"]), 2))
            for d in doses
        )
        await self.coordinator.async_dp_write_doses(parsed, self._resolve_day_mask(days))
