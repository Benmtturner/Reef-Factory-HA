"""Number platform for Reef Factory devices."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .const import FAMILY_DP, FAMILY_KH, UNIT_ML
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up numbers for whichever device family this entry is."""
    coordinator = entry.runtime_data
    if coordinator.family == FAMILY_DP:
        async_add_entities(
            [
                DpReservoirLevel(coordinator),
                DpCapacity(coordinator),
                DpCalibrationMeasured(coordinator),
            ]
        )
        return
    if coordinator.family != FAMILY_KH:
        return
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


class DpReservoirLevel(KhEntity, NumberEntity):
    """Current reservoir volume (mL) — set it after a refill."""

    _attr_name = "Reservoir Level"
    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0
    _attr_native_max_value = 20000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:cup-water"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reservoir_level")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.container_ml if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        state = self.coordinator.data
        capacity = state.capacity_ml if state and state.capacity_ml else value
        await self.coordinator.async_dp_set_container(value, capacity)


class DpCapacity(KhEntity, NumberEntity):
    """Container capacity (mL)."""

    _attr_name = "Container Capacity"
    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0
    _attr_native_max_value = 20000
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:cup-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "container_capacity")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.capacity_ml if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        state = self.coordinator.data
        current = state.container_ml if state and state.container_ml else 0
        await self.coordinator.async_dp_set_container(current, value)


class DpCalibrationMeasured(KhEntity, NumberEntity):
    """Enter the volume measured during a calibration run — setting it submits
    the calibration (do Fill Circuit → Run Calibration → catch the output first)."""

    _attr_name = "Calibration Measured"
    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.01
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:beaker-plus-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calibration_measured")
        self._value: float | None = None

    @property
    def native_value(self) -> float | None:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        await self.coordinator.async_dp_calibration_submit(value)
        self.async_write_ha_state()
