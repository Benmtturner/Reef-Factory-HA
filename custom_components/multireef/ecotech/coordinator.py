"""Coordinator for one EcoTech bridge — polls it and exposes the Mobius devices.

Unlike the Reef Factory coordinator (one persistent socket per device), a bridge
is a hub: one HTTP endpoint fronting many BLE devices. So this is a normal polling
DataUpdateCoordinator whose data is a dict of per-device records keyed by a stable
identity (serial, or MAC when no serial is advertised). Devices with rotating BLE
addresses keep the same identity across polls; commands re-resolve the current MAC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import CONF_BRIDGE_HOST
from .bridge import BridgeDevice, BridgeError, DeviceState, MobiusBridge
from .const import CONTROLLABLE_TYPES, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class DeviceRecord:
    """One Mobius device as the bridge currently sees it, plus its live state."""

    device: BridgeDevice
    state: DeviceState | None  # None for devices we don't poll (unsupported models)


class EcoTechCoordinator(DataUpdateCoordinator[dict[str, DeviceRecord]]):
    """Polls a single bridge; one config entry == one bridge (a hub)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.host: str = entry.data[CONF_BRIDGE_HOST]
        super().__init__(
            hass,
            _LOGGER,
            name=f"multireef_bridge_{self.host}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.entry = entry
        self.bridge = MobiusBridge(async_get_clientsession(hass), self.host)
        self._bridge_info: dict = {}

    @property
    def bridge_info(self) -> dict:
        """Last /health payload (fw, ip, rssi, heap …)."""
        return self._bridge_info

    async def _async_update_data(self) -> dict[str, DeviceRecord]:
        try:
            self._bridge_info = await self.bridge.health()
            devices = await self.bridge.devices()
        except BridgeError as err:
            raise UpdateFailed(f"bridge {self.host} unreachable: {err}") from err

        records: dict[str, DeviceRecord] = {}
        for dev in devices:
            state: DeviceState | None = None
            if dev.type in CONTROLLABLE_TYPES:
                try:
                    state = await self.bridge.state(dev.mac)
                except BridgeError as err:
                    _LOGGER.debug("state read failed for %s: %s", dev.mac, err)
            records[dev.identity] = DeviceRecord(device=dev, state=state)
        return records

    def record(self, identity: str) -> DeviceRecord | None:
        return (self.data or {}).get(identity)

    def controllable_devices(self) -> list[BridgeDevice]:
        """The devices we build entities for (found so far)."""
        return [
            rec.device
            for rec in (self.data or {}).values()
            if rec.device.type in CONTROLLABLE_TYPES
        ]

    def _mac_for(self, identity: str) -> str | None:
        """Resolve a stable identity to its current MAC (handles address rotation)."""
        rec = self.record(identity)
        return rec.device.mac if rec else None

    async def _apply(self, identity: str, action) -> None:
        """Run a bridge write for a device, then refresh just that device."""
        mac = self._mac_for(identity)
        if mac is None:
            _LOGGER.warning("no device %s to command", identity)
            return
        try:
            await action(mac)
        except BridgeError as err:
            _LOGGER.error("command to %s failed: %s", identity, err)
            raise
        await self._refresh_one(identity, mac)

    async def _refresh_one(self, identity: str, mac: str) -> None:
        """Re-read one device and push the update (cheaper than a full poll)."""
        try:
            state = await self.bridge.state(mac)
        except BridgeError:
            return
        data = dict(self.data or {})
        rec = data.get(identity)
        if rec is not None:
            data[identity] = DeviceRecord(device=rec.device, state=state)
            self.async_set_updated_data(data)

    async def async_set_scene(self, identity: str, scene: int) -> None:
        await self._apply(identity, lambda mac: self.bridge.set_scene(mac, scene))

    async def async_set_speed(self, identity: str, percent: int) -> None:
        await self._apply(identity, lambda mac: self.bridge.set_speed(mac, percent))

    async def async_set_mode(self, identity: str, mode: int) -> None:
        await self._apply(identity, lambda mac: self.bridge.set_mode(mac, mode))

    async def async_run_schedule(self, identity: str) -> None:
        await self._apply(identity, lambda mac: self.bridge.run_schedule(mac))
