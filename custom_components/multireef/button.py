"""Button platform for the KH Keeper."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .const import FAMILY_DP, FAMILY_KH
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechBridgeEntity
from .entity import KhEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons for whichever device family this entry is."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, EcoTechCoordinator):
        async_add_entities([EcoTechRefreshButton(coordinator)])
        return
    if coordinator.family == FAMILY_DP:
        async_add_entities(
            [
                DpStopRefillButton(coordinator),
                DpFillCircuitButton(coordinator),
                DpCalibrationRunButton(coordinator),
            ]
        )
        return
    if coordinator.family != FAMILY_KH:
        return
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


class DpStopRefillButton(KhEntity, ButtonEntity):
    """Cancel the active/pending manual refill."""

    _attr_name = "Stop Refill"
    _attr_icon = "mdi:stop-circle-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "stop_refill")

    async def async_press(self) -> None:
        await self.coordinator.async_dp_stop_refill()


class DpFillCircuitButton(KhEntity, ButtonEntity):
    """Calibration step 1: prime the tube (runs the pump)."""

    _attr_name = "Fill Circuit"
    _attr_icon = "mdi:pipe"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fill_circuit")

    async def async_press(self) -> None:
        await self.coordinator.async_dp_calibration_fill()


class DpCalibrationRunButton(KhEntity, ButtonEntity):
    """Calibration step 2: run the pump ~30 s (dispense into a cup, then submit ml)."""

    _attr_name = "Run Calibration"
    _attr_icon = "mdi:progress-wrench"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "calibration_run")

    async def async_press(self) -> None:
        await self.coordinator.async_dp_calibration_run()


class EcoTechRefreshButton(EcoTechBridgeEntity, ButtonEntity):
    """Pull current state from the pump(s) now — the on-demand model has no timer."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: EcoTechCoordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
