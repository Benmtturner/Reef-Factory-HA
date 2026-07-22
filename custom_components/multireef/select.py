"""Select platform — EcoTech scene/wave mode + KH Keeper measurement interval."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FAMILY_KH
from .ecotech.const import SCENE_SCHEDULE, SCENES, WAVE_MODES
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechDeviceEntity
from .entity import KhEntity
from .protocol import KH_INTERVAL_CUSTOM, KH_INTERVALS, kh_interval_label


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up selects for whichever device family this entry is."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, EcoTechCoordinator):
        entities: list[SelectEntity] = []
        for device in coordinator.controllable_devices():
            entities.append(EcoTechSceneSelect(coordinator, device))
            entities.append(EcoTechModeSelect(coordinator, device))
        async_add_entities(entities)
        return
    if getattr(coordinator, "family", None) == FAMILY_KH:
        async_add_entities([KhIntervalSelect(coordinator)])


class KhIntervalSelect(KhEntity, SelectEntity):
    """Automatic measurement interval (1 h … 12 h / Off).

    The byte↔label map beyond 1 h is provisional (SPA option order) — the raw
    code is exposed as an attribute so it can be cross-checked in the RF app.
    "Custom" (device-side scheduled time) shows if set there, but isn't settable
    from HA yet.
    """

    _attr_name = "Measurement Interval"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "measurement_interval")

    @property
    def options(self) -> list[str]:
        opts = list(KH_INTERVALS.values())
        state = self.coordinator.data
        if state is not None and state.interval_code == KH_INTERVAL_CUSTOM:
            opts.append("Custom")
        return opts

    @property
    def current_option(self) -> str | None:
        state = self.coordinator.data
        return kh_interval_label(state.interval_code) if state else None

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.data
        return {"raw_code": state.interval_code} if state else {}

    async def async_select_option(self, option: str) -> None:
        code = next((k for k, v in KH_INTERVALS.items() if v == option), None)
        if code is None:  # "Custom" — not settable from HA yet
            return
        await self.coordinator.async_kh_set_interval(code)


def _id_for(options: dict[int, str], label: str) -> int | None:
    return next((k for k, v in options.items() if v == label), None)


class EcoTechSceneSelect(EcoTechDeviceEntity, SelectEntity):
    """Active scene: Schedule / Feed / All Off / … .

    Picking "Schedule" resumes the schedule via run-schedule (the protocol's
    return-to-schedule op), not a scene write.
    """

    _attr_name = "Scene"
    _attr_icon = "mdi:playlist-play"
    _attr_options = list(SCENES.values())

    def __init__(self, coordinator: EcoTechCoordinator, device) -> None:
        super().__init__(coordinator, device, "scene")

    @property
    def current_option(self) -> str | None:
        state = self._state
        return SCENES.get(state.scene) if state else None

    async def async_select_option(self, option: str) -> None:
        scene_id = _id_for(SCENES, option)
        if scene_id is None:
            return
        if scene_id == SCENE_SCHEDULE:
            await self.coordinator.async_run_schedule(self._identity)
        else:
            await self.coordinator.async_set_scene(self._identity, scene_id)


class EcoTechModeSelect(EcoTechDeviceEntity, SelectEntity):
    """Wave mode of the running schedule program (Constant / ReefCrest / …)."""

    _attr_name = "Wave Mode"
    _attr_icon = "mdi:sine-wave"
    _attr_options = list(WAVE_MODES.values())

    def __init__(self, coordinator: EcoTechCoordinator, device) -> None:
        super().__init__(coordinator, device, "wave_mode")

    @property
    def current_option(self) -> str | None:
        state = self._state
        return WAVE_MODES.get(state.mode) if state else None

    async def async_select_option(self, option: str) -> None:
        mode_id = _id_for(WAVE_MODES, option)
        if mode_id is not None:
            await self.coordinator.async_set_mode(self._identity, mode_id)
