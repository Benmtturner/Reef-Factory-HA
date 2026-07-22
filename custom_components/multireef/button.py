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
from .protocol import KH_CIRCUIT_LABELS
from .redsea.ato import RedSeaAtoCoordinator
from .redsea.coordinator import RedSeaDoserCoordinator
from .redsea.entity import RedSeaAtoEntity, RedSeaDoserEntity, RedSeaHeadEntity


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
    if isinstance(coordinator, RedSeaDoserCoordinator):
        buttons: list[ButtonEntity] = [RedSeaRefreshButton(coordinator)]
        buttons += [
            RedSeaDoseNowButton(coordinator, head)
            for head in range(1, coordinator.heads_nb + 1)
        ]
        async_add_entities(buttons)
        return
    if isinstance(coordinator, RedSeaAtoCoordinator):
        async_add_entities([RedSeaAtoRefreshButton(coordinator)])
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
            KhMeasurePhButton(coordinator),
            KhCalStartButton(coordinator, "aquarium"),
            KhCalStartButton(coordinator, "reagent_a"),
            KhCalStartButton(coordinator, "ro"),
            KhCalStopButton(coordinator),
            KhCalResetButton(coordinator),
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


class KhMeasurePhButton(KhEntity, ButtonEntity):
    """Read pH now — no reagent used, safe any time. Result lands as the pH
    sensor's live_ph attribute."""

    _attr_name = "Measure pH"
    _attr_icon = "mdi:ph"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "measure_ph")

    async def async_press(self) -> None:
        await self.coordinator.async_kh_measure_ph()


class KhCalStartButton(KhEntity, ButtonEntity):
    """Start calibrating one fluid circuit's pump.

    Flow (mirrors the RF app): start → the pump runs and the device counts
    down → measure what it dispensed → enter it in Calibration Measured.
    """

    _attr_icon = "mdi:progress-wrench"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, circuit: str) -> None:
        super().__init__(coordinator, f"cal_start_{circuit}")
        self._circuit = circuit
        self._attr_name = f"Calibrate {KH_CIRCUIT_LABELS[circuit]}"

    async def async_press(self) -> None:
        await self.coordinator.async_kh_calibration_start(self._circuit)


class KhCalStopButton(KhEntity, ButtonEntity):
    """Stop the running calibration (the last circuit started)."""

    _attr_name = "Stop Calibration"
    _attr_icon = "mdi:stop-circle-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cal_stop")

    async def async_press(self) -> None:
        await self.coordinator.async_kh_calibration_stop()


class KhCalResetButton(KhEntity, ButtonEntity):
    """Reset pump calibration to factory values."""

    _attr_name = "Reset Calibration"
    _attr_icon = "mdi:backup-restore"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cal_reset")

    async def async_press(self) -> None:
        await self.coordinator.async_kh_calibration_reset()


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


# ---------------------------------------------------------------------------
# Red Sea (ReefBeat) ReefDose buttons
# ---------------------------------------------------------------------------


class RedSeaDoseNowButton(RedSeaHeadEntity, ButtonEntity):
    """Dose the head's manual-dose volume now (POST /head/{n}/manual)."""

    _attr_icon = "mdi:water-plus"

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "dose_now", "Dose Now")

    async def async_press(self) -> None:
        await self.coordinator.async_manual_dose(self._head)


class RedSeaRefreshButton(RedSeaDoserEntity, ButtonEntity):
    """Pull fresh state from the doser now (between the gentle background polls)."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()


class RedSeaAtoRefreshButton(RedSeaAtoEntity, ButtonEntity):
    """Pull fresh state from the ATO now (between the gentle background polls)."""

    _attr_name = "Refresh"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "refresh")

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
