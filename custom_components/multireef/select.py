"""Select platform — EcoTech scene and wave mode.

Only EcoTech bridge entries use selects; Reef Factory entries have none, so this
platform is a no-op for them.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ecotech.const import SCENE_SCHEDULE, SCENES, WAVE_MODES
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create scene + wave-mode selects for each controllable Mobius device."""
    coordinator = entry.runtime_data
    if not isinstance(coordinator, EcoTechCoordinator):
        return
    entities: list[SelectEntity] = []
    for device in coordinator.controllable_devices():
        entities.append(EcoTechSceneSelect(coordinator, device))
        entities.append(EcoTechModeSelect(coordinator, device))
    async_add_entities(entities)


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
