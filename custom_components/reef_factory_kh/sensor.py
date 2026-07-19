"""Sensor platform for Reef Factory devices (KH Keeper + single-head doser)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from . import KhConfigEntry
from .const import FAMILY_DP, UNIT_DKH, UNIT_ML
from .entity import KhEntity
from .protocol import MEASUREMENT_STATES, DpState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for whichever device family this entry is."""
    coordinator = entry.runtime_data

    if coordinator.family == FAMILY_DP:
        entities: list[SensorEntity] = [DpSensor(coordinator, desc) for desc in DP_SENSORS]
        entities += [DpDosedToday(coordinator), DpNextDose(coordinator)]
        async_add_entities(entities)
        return

    async_add_entities(
        [
            KhCarbonateHardnessSensor(coordinator),
            KhPhSensor(coordinator),
            KhLastMeasurementSensor(coordinator),
            KhMeasurementStatusSensor(coordinator),
            KhAlertThresholdSensor(coordinator, "alert_low", "Alert Low", "alert_low_dkh"),
            KhAlertThresholdSensor(coordinator, "alert_high", "Alert High", "alert_high_dkh"),
        ]
    )


# ---------------------------------------------------------------------------
# KH Keeper sensors
# ---------------------------------------------------------------------------


class KhCarbonateHardnessSensor(KhEntity, SensorEntity):
    """Current carbonate hardness (dKH)."""

    _attr_translation_key = "carbonate_hardness"
    _attr_name = "Carbonate Hardness"
    _attr_native_unit_of_measurement = UNIT_DKH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:test-tube"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "carbonate_hardness")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.kh_dkh if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        return {
            "kh_change_dkh": state.kh_change_dkh,
            "alert_low_dkh": state.alert_low_dkh,
            "alert_high_dkh": state.alert_high_dkh,
            "history": [
                {
                    "kh_dkh": m.kh_dkh,
                    "ph": m.ph,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "alert": m.alert,
                }
                for m in state.history
            ],
        }


class KhPhSensor(KhEntity, SensorEntity):
    """pH at the most recent measurement."""

    _attr_name = "pH"
    _attr_device_class = SensorDeviceClass.PH
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ph")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.ph if self.coordinator.data else None


class KhLastMeasurementSensor(KhEntity, SensorEntity):
    """Timestamp of the most recent measurement."""

    _attr_name = "Last Measurement"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "last_measurement")

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.data.last_measurement if self.coordinator.data else None


class KhMeasurementStatusSensor(KhEntity, SensorEntity):
    """Live measurement state, with progress % as an attribute."""

    _attr_name = "Measurement Status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(MEASUREMENT_STATES.values())
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "measurement_status")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.measurement_status if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        return {
            "progress": state.measurement_progress,
            "state_code": state.measurement_state,
        }


class KhAlertThresholdSensor(KhEntity, SensorEntity):
    """A configured KH alert threshold (low/high), diagnostic."""

    _attr_native_unit_of_measurement = UNIT_DKH
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:arrow-collapse-vertical"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator, key: str, name: str, attr: str) -> None:
        super().__init__(coordinator, key)
        self._attr_name = name
        self._value_attr = attr

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return getattr(self.coordinator.data, self._value_attr)


# ---------------------------------------------------------------------------
# Single-head doser sensors
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class DpSensorDescription(SensorEntityDescription):
    """Describes a doser sensor with a value extractor."""

    value_fn: Callable[[DpState], StateType | datetime]


DP_SENSORS: tuple[DpSensorDescription, ...] = (
    DpSensorDescription(
        key="container_level",
        name="Container Level",
        native_unit_of_measurement=UNIT_ML,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cup-water",
        suggested_display_precision=0,
        value_fn=lambda s: s.container_ml,
    ),
    DpSensorDescription(
        key="reservoir",
        name="Reservoir",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        suggested_display_precision=0,
        value_fn=lambda s: s.reservoir_pct,
    ),
    DpSensorDescription(
        key="capacity",
        name="Capacity",
        native_unit_of_measurement=UNIT_ML,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cup-outline",
        suggested_display_precision=0,
        value_fn=lambda s: s.capacity_ml,
    ),
    DpSensorDescription(
        key="daily_total",
        name="Today's Dose Total",
        native_unit_of_measurement=UNIT_ML,
        icon="mdi:beaker-outline",
        suggested_display_precision=2,
        value_fn=lambda s: s.daily_total_ml,
    ),
    DpSensorDescription(
        key="dosed_since_refill",
        name="Dosed Since Refill",
        native_unit_of_measurement=UNIT_ML,
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:beaker-plus-outline",
        suggested_display_precision=2,
        value_fn=lambda s: s.dosed_since_refill_ml,
    ),
    DpSensorDescription(
        key="dose_count",
        name="Number of Doses",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda s: s.dose_count,
    ),
    DpSensorDescription(
        key="per_dose",
        name="Per-Dose Amount",
        native_unit_of_measurement=UNIT_ML,
        icon="mdi:eyedropper-variant",
        suggested_display_precision=2,
        value_fn=lambda s: s.per_dose_ml,
    ),
    DpSensorDescription(
        key="last_dose",
        name="Last Dose",
        native_unit_of_measurement=UNIT_ML,
        icon="mdi:water",
        suggested_display_precision=2,
        value_fn=lambda s: s.last_dose_ml,
    ),
    DpSensorDescription(
        key="last_dose_time",
        name="Last Dose Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-check-outline",
        value_fn=lambda s: s.last_dose_at,
    ),
    DpSensorDescription(
        key="time_left",
        name="Time Left",
        native_unit_of_measurement="d",
        icon="mdi:calendar-clock",
        suggested_display_precision=1,
        value_fn=lambda s: s.time_left_days,
    ),
    DpSensorDescription(
        key="dosing_days",
        name="Dosing Days",
        icon="mdi:calendar-week",
        value_fn=lambda s: ", ".join(s.active_days) if s.active_days else "None",
    ),
    DpSensorDescription(
        key="next_calibration",
        name="Next Calibration",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:progress-wrench",
        value_fn=lambda s: s.calibration_date,
    ),
)


class DpSensor(KhEntity, SensorEntity):
    """A single decoded doser sensor."""

    entity_description: DpSensorDescription

    def __init__(self, coordinator, description: DpSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class DpDosedToday(KhEntity, SensorEntity):
    """Volume actually dosed today, INCLUDING canceled/partial doses.

    The device only logs *completed* doses to its history, but its running
    ``dosed_since_refill_ml`` counter ticks up on every pour — partials included.
    We accumulate that counter's rise since local midnight, so a canceled dose
    still counts (matching the RF app), ignoring the downward jump when the
    container is refilled. The ``logged_total`` attribute keeps the history-only
    figure for reference.

    State is in-memory: on an HA restart it re-baselines to today's logged total
    (partials dosed before the restart are lost) and never reads below the log.
    """

    _attr_name = "Dosed Today"
    _attr_native_unit_of_measurement = UNIT_ML
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:beaker-check-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dosed_today")
        self._accum: float | None = None
        self._prev_counter: float | None = None
        self._day: date | None = None

    def _logged_today(self, state) -> float:
        today = dt_util.now().date()
        return round(
            sum(d.volume_ml for d in state.history if d.timestamp and d.timestamp.date() == today),
            2,
        )

    @property
    def native_value(self) -> float | None:
        # Idempotent accumulation: re-processing the same frame is a no-op because
        # _prev_counter advances to the value we just consumed (delta becomes 0).
        state = self.coordinator.data
        if state is None:
            return round(self._accum, 2) if self._accum is not None else None
        today = dt_util.now().date()
        logged = self._logged_today(state)
        counter = state.dosed_since_refill_ml
        if self._day != today:
            # New day or first run: baseline from today's logged doses.
            self._day = today
            self._accum = logged
            self._prev_counter = counter
        else:
            if counter is not None and self._prev_counter is not None:
                delta = counter - self._prev_counter
                if delta > 0:  # a pour (incl. partials); ignore refill resets (<0)
                    self._accum = (self._accum if self._accum is not None else logged) + delta
                self._prev_counter = counter
            elif counter is not None:
                self._prev_counter = counter
            # Floor: never read below the logged total (covers a mid-day refill
            # reset, a missed delta, or the very first frame after startup).
            if self._accum is None or self._accum < logged:
                self._accum = logged
        return round(self._accum, 2) if self._accum is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        return {
            "logged_total": self._logged_today(state),
            "history": [
                {
                    "time": d.timestamp.isoformat() if d.timestamp else None,
                    "ml": d.volume_ml,
                    "type": "manual" if d.manual else "scheduled",
                }
                for d in state.history
            ],
        }


class DpNextDose(KhEntity, SensorEntity):
    """Timestamp of the next scheduled dose, with amount + full schedule."""

    _attr_name = "Next Dose"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "next_dose")

    def _next(self):
        state = self.coordinator.data
        if state is None:
            return None, None
        now = dt_util.now()
        nxt = state.next_dose(now.hour * 60 + now.minute)
        return now, nxt

    @property
    def native_value(self) -> datetime | None:
        now, nxt = self._next()
        if nxt is None:
            return None
        minute, _ml = nxt
        target = now.replace(hour=minute // 60, minute=minute % 60, second=0, microsecond=0)
        if minute <= now.hour * 60 + now.minute:
            target += timedelta(days=1)
        return target

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self.coordinator.data
        if state is None:
            return {}
        _now, nxt = self._next()
        return {
            "amount_ml": nxt[1] if nxt else None,
            "schedule": [
                {"time": f"{m // 60:02d}:{m % 60:02d}", "ml": v} for m, v in state.timetable
            ],
        }
