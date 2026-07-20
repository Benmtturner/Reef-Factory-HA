"""Switch platform for Multi Reef.

Currently only the Red Sea ReefDose uses switches — one per head to enable or
disable its automatic dosing schedule. Other families don't forward this platform,
but the setup guards by coordinator type regardless.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import EntityCategory

from . import KhConfigEntry
from .redsea.coordinator import RedSeaDoserCoordinator
from .redsea.entity import RedSeaDoserEntity, RedSeaHeadEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for a Red Sea ReefDose."""
    coordinator = entry.runtime_data
    if not isinstance(coordinator, RedSeaDoserCoordinator):
        return
    switches: list[SwitchEntity] = [RedSeaHeadsSwitch(coordinator)]
    for head in range(1, coordinator.heads_nb + 1):
        switches += [
            RedSeaScheduleSwitch(coordinator, head),
            RedSeaFoodHeadSwitch(coordinator, head),
            RedSeaMonitorSwitch(coordinator, head),
            RedSeaPrimingSwitch(coordinator, head),
        ]
    async_add_entities(switches)


class RedSeaHeadsSwitch(RedSeaDoserEntity, SwitchEntity):
    """Automatic dosing on (auto) / off (all heads off) — the app's power toggle."""

    _attr_name = "Automatic Dosing"
    _attr_icon = "mdi:auto-mode"

    def __init__(self, coordinator: RedSeaDoserCoordinator) -> None:
        super().__init__(coordinator, "automatic_dosing")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.heads_on if self.coordinator.data else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_heads_on(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_heads_on(False)


class RedSeaScheduleSwitch(RedSeaHeadEntity, SwitchEntity):
    """Enable/disable a head's automatic dosing schedule."""

    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: RedSeaDoserCoordinator, head: int) -> None:
        super().__init__(coordinator, head, "schedule", "Schedule")

    @property
    def is_on(self) -> bool | None:
        head = self._head_state
        return head.schedule_enabled if head else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_schedule_enabled(self._head, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_schedule_enabled(self._head, False)


class RedSeaFoodHeadSwitch(RedSeaHeadEntity, SwitchEntity):
    """Mark a head as the feed-mode head (its dose triggers Aquarium Feed mode)."""

    _attr_icon = "mdi:fish"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: RedSeaDoserCoordinator, head: int) -> None:
        super().__init__(coordinator, head, "food_head", "Food Head")

    @property
    def is_on(self) -> bool | None:
        head = self._head_state
        return head.is_food_head if head else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_food_head(self._head, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_food_head(self._head, False)


class RedSeaMonitorSwitch(RedSeaHeadEntity, SwitchEntity):
    """Supplement-level monitor for a head (tracks remaining volume, low alerts)."""

    _attr_icon = "mdi:gauge"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: RedSeaDoserCoordinator, head: int) -> None:
        super().__init__(coordinator, head, "monitor", "Supplement Monitor")

    @property
    def is_on(self) -> bool | None:
        head = self._head_state
        return head.slm if head else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_slm(self._head, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_slm(self._head, False)


class RedSeaPrimingSwitch(RedSeaHeadEntity, SwitchEntity):
    """Prime a head's dosing tube — runs the pump while on (assumed state).

    The device exposes no priming-state read, so this is optimistic: turning it on
    starts priming, off stops it. Watch the tube and switch off when it reaches the
    outlet tip.
    """

    _attr_icon = "mdi:pipe"
    _attr_assumed_state = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: RedSeaDoserCoordinator, head: int) -> None:
        super().__init__(coordinator, head, "priming", "Priming")
        self._priming = False

    @property
    def is_on(self) -> bool:
        return self._priming

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._priming = True
        self.async_write_ha_state()
        await self.coordinator.async_set_priming(self._head, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._priming = False
        self.async_write_ha_state()
        await self.coordinator.async_set_priming(self._head, False)
