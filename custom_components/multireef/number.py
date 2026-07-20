"""Number platform for Reef Factory devices."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .const import FAMILY_DP, FAMILY_KH, UNIT_ML
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechDeviceEntity
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up numbers for whichever device family this entry is."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, EcoTechCoordinator):
        async_add_entities(
            EcoTechSpeedNumber(coordinator, device)
            for device in coordinator.controllable_devices()
        )
        return
    if coordinator.family == FAMILY_DP:
        async_add_entities([DpReservoirLevel(coordinator), DpCapacity(coordinator)])
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
        # Contents can never exceed the container capacity.
        await self.coordinator.async_dp_set_container(min(value, capacity), capacity)


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
        # Capacity must be positive (0 makes the device's fill-% divide by zero)
        # and never below the current contents.
        capacity = max(1.0, value)
        state = self.coordinator.data
        current = min(state.container_ml if state and state.container_ml else 0, capacity)
        await self.coordinator.async_dp_set_container(current, capacity)


class EcoTechSpeedNumber(EcoTechDeviceEntity, NumberEntity):
    """Wave pump speed, 0–100% (read-modify-write of the 0x197 program)."""

    _attr_name = "Speed"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: EcoTechCoordinator, device) -> None:
        super().__init__(coordinator, device, "speed")

    @property
    def native_value(self) -> float | None:
        state = self._state
        return state.speed if state and state.speed >= 0 else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_speed(self._identity, int(round(value)))
