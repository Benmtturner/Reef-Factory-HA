"""Button platform for the KH Keeper."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KH Keeper buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            KhMeasureNowButton(coordinator),
            KhCancelButton(coordinator),
        ]
    )


class KhMeasureNowButton(KhEntity, ButtonEntity):
    """Trigger a measurement now (runs a full titration)."""

    _attr_name = "Measure Now"
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "measure_now")

    async def async_press(self) -> None:
        await self.coordinator.async_measure_now()


class KhCancelButton(KhEntity, ButtonEntity):
    """Cancel the measurement in progress."""

    _attr_name = "Cancel Measurement"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cancel_measurement")

    async def async_press(self) -> None:
        await self.coordinator.async_cancel_measurement()
