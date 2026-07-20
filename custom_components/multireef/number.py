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
from .redsea.const import (
    CONTAINER_MAX_ML,
    DAILY_DOSE_MAX_ML,
    DOSING_DELAY_MAX_S,
    MANUAL_DOSE_MAX_ML,
    STOCK_DAYS_MAX,
)
from .redsea.coordinator import RedSeaDoserCoordinator
from .redsea.entity import RedSeaDoserEntity, RedSeaHeadEntity


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
    if isinstance(coordinator, RedSeaDoserCoordinator):
        nums: list[NumberEntity] = [
            RedSeaDosingDelayNumber(coordinator),
            RedSeaStockDaysNumber(coordinator),
        ]
        for head in range(1, coordinator.heads_nb + 1):
            nums.append(RedSeaManualDoseNumber(coordinator, head))
            nums.append(RedSeaDailyDoseNumber(coordinator, head))
            nums.append(RedSeaContainerNumber(coordinator, head))
        async_add_entities(nums)
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


# ---------------------------------------------------------------------------
# Red Sea (ReefBeat) ReefDose numbers — per head
# ---------------------------------------------------------------------------


class RedSeaManualDoseNumber(RedSeaHeadEntity, NumberEntity):
    """Manual-dose volume (mL) — a local setpoint the Dose Now button uses.

    Held in the coordinator (not pushed to the device); pressing the head's
    Dose Now button doses exactly this amount.
    """

    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0.1
    _attr_native_max_value = MANUAL_DOSE_MAX_ML
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:eyedropper-variant"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "manual_dose", "Manual Dose")

    @property
    def available(self) -> bool:
        # A local setpoint — usable as long as the coordinator is alive, even if a
        # single poll missed (don't gate it on head state like device-backed ones).
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_manual_dose(self._head)

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_manual_dose(self._head, value)
        self.async_write_ha_state()


class RedSeaContainerNumber(RedSeaHeadEntity, NumberEntity):
    """Reservoir contents (mL) for a head — displays and writes to the device."""

    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0
    _attr_native_max_value = CONTAINER_MAX_ML
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:cup-water"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "container", "Container")

    @property
    def native_value(self) -> float | None:
        head = self._head_state
        return head.container_ml if head else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_container(self._head, value)


class RedSeaDailyDoseNumber(RedSeaHeadEntity, NumberEntity):
    """Dose-per-day target (mL) for a head — displays and writes ``schedule.dd``."""

    _attr_native_unit_of_measurement = UNIT_ML
    _attr_native_min_value = 0
    _attr_native_max_value = DAILY_DOSE_MAX_ML
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:target-variant"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "daily_dose", "Daily Dose")

    @property
    def native_value(self) -> float | None:
        head = self._head_state
        return head.daily_dose_ml if head else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_daily_dose(self._head, value)


class RedSeaDosingDelayNumber(RedSeaDoserEntity, NumberEntity):
    """Device dosing delay (seconds waited between dosing each head)."""

    _attr_name = "Dosing Delay"
    _attr_native_unit_of_measurement = "s"
    _attr_native_min_value = 0
    _attr_native_max_value = DOSING_DELAY_MAX_S
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:timer-sand"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dosing_delay")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.dosing_delay if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_dosing_delay(int(value))


class RedSeaStockDaysNumber(RedSeaDoserEntity, NumberEntity):
    """Supplement-volume-monitor alert threshold (days of stock remaining)."""

    _attr_name = "Stock Alert Days"
    _attr_native_unit_of_measurement = "d"
    _attr_native_min_value = 1
    _attr_native_max_value = STOCK_DAYS_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:calendar-alert"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "stock_alert_days")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.stock_alert_days if self.coordinator.data else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_stock_days(int(value))
