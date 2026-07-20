"""Update platform — OTA firmware for the EcoTech bridge.

The compiled firmware ships inside the integration (firmware/mobius_bridge.bin).
The entity compares the bridge's running version (from /health) against the
bundled BRIDGE_FW_VERSION and, on install, pushes the bundled image over Wi-Fi to
the bridge's /update endpoint — so a firmware update is a click in Home Assistant.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .ecotech.bridge import BridgeError
from .ecotech.const import BRIDGE_FW_VERSION
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import EcoTechBridgeEntity, bridge_device_info

_LOGGER = logging.getLogger(__name__)

_FIRMWARE = Path(__file__).parent / "firmware" / "mobius_bridge.bin"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the firmware update entity for an EcoTech bridge."""
    coordinator = entry.runtime_data
    if not isinstance(coordinator, EcoTechCoordinator):
        return
    async_add_entities([MobiusBridgeUpdate(coordinator)])


class MobiusBridgeUpdate(EcoTechBridgeEntity, UpdateEntity):
    """Firmware for the Multi Reef bridge — installs the bundled image over the air."""

    _attr_name = "Firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_release_url = "https://github.com/Benmtturner/Reef-Factory-HA"

    def __init__(self, coordinator: EcoTechCoordinator) -> None:
        super().__init__(coordinator, "firmware")

    @property
    def installed_version(self) -> str | None:
        fw = self.coordinator.bridge_info.get("fw")
        return str(fw) if fw else None

    @property
    def latest_version(self) -> str:
        return BRIDGE_FW_VERSION

    async def async_install(
        self, version: str | None, backup: bool, **kwargs
    ) -> None:
        if not _FIRMWARE.is_file():
            raise HomeAssistantError("Bundled bridge firmware is missing")
        data = await self.hass.async_add_executor_job(_FIRMWARE.read_bytes)
        try:
            await self.coordinator.bridge.upload_firmware(data)
        except BridgeError as err:
            raise HomeAssistantError(f"Bridge firmware update failed: {err}") from err
        _LOGGER.info("Pushed bridge firmware %s to %s", version, self.coordinator.host)
        # The bridge reboots (~15-30s). Wait for it to answer again, then refresh so
        # entities recover immediately (not after the 5-min poll) and update the hub
        # device's shown firmware — otherwise everything reads Unavailable/stale for
        # minutes right after an update.
        for _ in range(30):  # up to ~60s
            await asyncio.sleep(2)
            try:
                await self.coordinator.bridge.health()
                break
            except BridgeError:
                continue
        await self.coordinator.async_refresh()
        dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.coordinator.entry.entry_id,
            **bridge_device_info(self.coordinator),
        )
