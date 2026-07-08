"""Number platform for the KH Keeper."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KH Keeper numbers."""
    coordinator = entry.runtime_data
    async_add_entities([KhRemainingReagent(coordinator)])


class KhRemainingReagent(KhEntity, NumberEntity):
    """Remaining reagent — reads the live value, sets it via khSet/reagent."""

    _attr_name = "Remaining Reagent"
    _attr_native_unit_of_measurement = "mL"
    _attr_native_min_value = 0
    _attr_native_max_value = 2000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "remaining_reagent")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.reagent_ml if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_reagent(value)
