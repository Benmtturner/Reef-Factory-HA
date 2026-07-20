"""Sensor platform for Reef Factory devices (KH Keeper + single-head doser)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
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
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechBridgeEntity, EcoTechDeviceEntity
from .entity import KhEntity
from .protocol import MEASUREMENT_STATES, DpState
from .redsea.api import HeadState
from .redsea.coordinator import RedSeaDoserCoordinator
from .redsea.entity import RedSeaDoserEntity, RedSeaHeadEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for whichever device family this entry is."""
    coordinator = entry.runtime_data

    if isinstance(coordinator, EcoTechCoordinator):
        eco: list[SensorEntity] = [
            EcoTechBridgeSignalSensor(coordinator),
            EcoTechBridgeDevicesSensor(coordinator),
        ]
        eco += [
            EcoTechDeviceSignalSensor(coordinator, device)
            for device in coordinator.controllable_devices()
        ]
        async_add_entities(eco)
        return

    if isinstance(coordinator, RedSeaDoserCoordinator):
        rs: list[SensorEntity] = [RedSeaBatterySensor(coordinator)]
        for head in range(1, coordinator.heads_nb + 1):
            rs += [
                RedSeaHeadSensor(coordinator, head, desc)
                for desc in REDSEA_HEAD_SENSORS
            ]
            rs.append(RedSeaNextDoseSensor(coordinator, head))
            rs.append(RedSeaLastCalibratedSensor(coordinator, head))
        async_add_entities(rs)
        return

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
    """Total volume dosed today, read straight from the device's own daily counter.

    The device keeps a running daily dose total (resets ~midnight) that ticks up
    on EVERY pour including canceled/partial doses — the same figure the RF app
    shows as "TODAY". It is NOT container-derived (verified live: raising the
    container level left it unchanged), so we just read it. The timestamped log
    holds only *completed* doses, kept on the ``history``/``logged_total``
    attributes for reference; it will read lower than the headline whenever a
    dose was canceled mid-pour. Falls back to the logged sum if the counter reads
    garbage.
    """

    _attr_name = "Dosed Today"
    _attr_native_unit_of_measurement = UNIT_ML
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:beaker-check-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "dosed_today")

    def _logged_today(self, state) -> float:
        today = dt_util.now().date()
        return round(
            sum(d.volume_ml for d in state.history if d.timestamp and d.timestamp.date() == today),
            2,
        )

    @property
    def native_value(self) -> float | None:
        state = self.coordinator.data
        if state is None:
            return None
        if state.dosed_today_ml is not None:
            return state.dosed_today_ml
        return self._logged_today(state)  # fallback if the counter read is bad

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


# ---------------------------------------------------------------------------
# EcoTech (Mobius) sensors — the bridge hub + per-device diagnostics
# ---------------------------------------------------------------------------


class EcoTechBridgeSignalSensor(EcoTechBridgeEntity, SensorEntity):
    """Bridge Wi-Fi signal strength."""

    _attr_name = "Signal"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EcoTechCoordinator) -> None:
        super().__init__(coordinator, "wifi_signal")

    @property
    def native_value(self) -> StateType:
        rssi = self.coordinator.bridge_info.get("rssi")
        return rssi if isinstance(rssi, (int, float)) else None


class EcoTechBridgeDevicesSensor(EcoTechBridgeEntity, SensorEntity):
    """How many Mobius devices the bridge currently sees."""

    _attr_name = "Devices"
    _attr_icon = "mdi:bluetooth"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EcoTechCoordinator) -> None:
        super().__init__(coordinator, "device_count")

    @property
    def native_value(self) -> StateType:
        return len(self.coordinator.data or {})


class EcoTechDeviceSignalSensor(EcoTechDeviceEntity, SensorEntity):
    """BLE signal strength of one Mobius device (available even if state fails)."""

    _attr_name = "Signal"
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EcoTechCoordinator, device) -> None:
        super().__init__(coordinator, device, "ble_signal")

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._record is not None

    @property
    def native_value(self) -> StateType:
        rec = self._record
        return rec.device.rssi if rec else None


# ---------------------------------------------------------------------------
# Red Sea (ReefBeat) ReefDose sensors — per head + a device battery sensor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class RedSeaHeadSensorDescription(SensorEntityDescription):
    """Describes a per-head ReefDose sensor with a value extractor."""

    value_fn: Callable[[HeadState], StateType]


REDSEA_HEAD_SENSORS: tuple[RedSeaHeadSensorDescription, ...] = (
    RedSeaHeadSensorDescription(
        key="dosed_today",
        name="Dosed Today",
        native_unit_of_measurement=UNIT_ML,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:beaker-check-outline",
        suggested_display_precision=2,
        value_fn=lambda h: h.dosed_today_ml,
    ),
    RedSeaHeadSensorDescription(
        key="daily_target",
        name="Daily Target",
        native_unit_of_measurement=UNIT_ML,
        icon="mdi:target-variant",
        suggested_display_precision=2,
        value_fn=lambda h: h.daily_dose_ml,
    ),
    RedSeaHeadSensorDescription(
        key="doses_per_day",
        name="Doses per Day",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:counter",
        value_fn=lambda h: h.daily_doses,
    ),
    RedSeaHeadSensorDescription(
        key="remaining_days",
        name="Remaining Days",
        native_unit_of_measurement="d",
        icon="mdi:calendar-clock",
        value_fn=lambda h: h.remaining_days,
    ),
    RedSeaHeadSensorDescription(
        key="stock_level",
        name="Stock Level",
        icon="mdi:gauge",
        value_fn=lambda h: h.stock_level,
    ),
    RedSeaHeadSensorDescription(
        key="supplement",
        name="Supplement",
        icon="mdi:bottle-tonic-outline",
        value_fn=lambda h: h.supplement,
    ),
)


class RedSeaHeadSensor(RedSeaHeadEntity, SensorEntity):
    """A single decoded per-head ReefDose sensor."""

    entity_description: RedSeaHeadSensorDescription

    def __init__(
        self, coordinator, head: int, description: RedSeaHeadSensorDescription
    ) -> None:
        super().__init__(coordinator, head, description.key, description.name)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        head = self._head_state
        return self.entity_description.value_fn(head) if head else None


class RedSeaNextDoseSensor(RedSeaHeadEntity, SensorEntity):
    """Next scheduled dose time for a head (None when the schedule is off).

    Handles the schedule types the device exposes: ``single`` (one dose/day at
    ``schedule.time``) and ``hourly`` (every hour at ``schedule.min``). ``custom``
    and ``timer`` schedules aren't modelled yet, so those report None.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "next_dose", "Next Dose")

    @property
    def native_value(self) -> datetime | None:
        head = self._head_state
        if head is None or not head.schedule_enabled or not head.days:
            return None
        now = dt_util.now()
        if head.schedule_type == "single":
            hour, minute = divmod(head.dose_time_min, 60)
            for offset in range(8):
                day = now + timedelta(days=offset)
                if day.isoweekday() in head.days:
                    target = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target > now:
                        return target
            return None
        if head.schedule_type == "hourly":
            # Dose every hour at :min — first future :min hour on an active day.
            base = now.replace(minute=head.schedule_min % 60, second=0, microsecond=0)
            for offset in range(24 * 8):
                target = base + timedelta(hours=offset)
                if target > now and target.isoweekday() in head.days:
                    return target
            return None
        return None  # custom / timer not modelled yet

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        head = self._head_state
        if head is None:
            return {}
        return {"schedule_type": head.schedule_type, "doses_per_day": head.daily_doses}


class RedSeaLastCalibratedSensor(RedSeaHeadEntity, SensorEntity):
    """When a head was last calibrated."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:progress-wrench"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, head: int) -> None:
        super().__init__(coordinator, head, "last_calibrated", "Last Calibrated")

    @property
    def native_value(self) -> datetime | None:
        head = self._head_state
        if head is None or head.last_calibrated <= 0:
            return None
        return dt_util.utc_from_timestamp(head.last_calibrated)


class RedSeaBatterySensor(RedSeaDoserEntity, SensorEntity):
    """RTC-backup battery status ('low' = coin cell dying → clock drift)."""

    _attr_name = "Battery"
    _attr_icon = "mdi:battery-alert-variant-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "battery")

    @property
    def native_value(self) -> StateType:
        return self.coordinator.data.battery_level if self.coordinator.data else None
