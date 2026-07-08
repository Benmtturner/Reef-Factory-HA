"""Sensor platform for the KH Keeper."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KhConfigEntry
from .const import UNIT_DKH
from .entity import KhEntity
from .protocol import MEASUREMENT_STATES


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KhConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KH Keeper sensors."""
    coordinator = entry.runtime_data
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
