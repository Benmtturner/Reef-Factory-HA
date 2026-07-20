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
from .const import CONTROLLABLE_TYPES, POLL_INTERVAL

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
        # Gentle 5-min background poll plus a Refresh button — the pump and the
        # Mobius app are left alone between polls. The advert is identity-only, so a
        # poll is the only way to catch state changed elsewhere (e.g. in the app).
        super().__init__(
            hass,
            _LOGGER,
            name=f"multireef_bridge_{self.host}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
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

        prev = self.data or {}
        records: dict[str, DeviceRecord] = {}
        for dev in devices:
            state: DeviceState | None = None
            if dev.type in CONTROLLABLE_TYPES:
                try:
                    state = await self.bridge.state(dev.target)
                except BridgeError as err:
                    # A single connect-on-demand miss (pump briefly busy or the app
                    # grabbed it) shouldn't flap the entity offline — carry the
                    # last-known state forward until the next poll succeeds.
                    _LOGGER.debug("state read failed for %s: %s", dev.mac, err)
                    prev_rec = prev.get(dev.identity)
                    state = prev_rec.state if prev_rec else None
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

    def _target_for(self, identity: str) -> str | None:
        """Bridge query fragment for a device — serial-preferred; the bridge resolves
        it to the current address, so a rolled MAC doesn't matter."""
        rec = self.record(identity)
        return rec.device.target if rec else None

    async def _apply(self, identity: str, action) -> None:
        """Run a bridge write for a device, then refresh just that device."""
        target = self._target_for(identity)
        if target is None:
            _LOGGER.warning("no device %s to command", identity)
            return
        try:
            await action(target)
        except BridgeError as err:
            _LOGGER.error("command to %s failed: %s", identity, err)
            raise
        await self._refresh_one(identity)

    async def _refresh_one(self, identity: str) -> None:
        """Re-read one device and push the update (cheaper than a full poll)."""
        target = self._target_for(identity)
        if target is None:
            return
        try:
            state = await self.bridge.state(target)
        except BridgeError:
            return
        data = dict(self.data or {})
        rec = data.get(identity)
        if rec is not None:
            data[identity] = DeviceRecord(device=rec.device, state=state)
            self.async_set_updated_data(data)

    async def async_set_scene(self, identity: str, scene: int) -> None:
        await self._apply(identity, lambda t: self.bridge.set_scene(t, scene))

    async def async_set_speed(self, identity: str, percent: int) -> None:
        await self._apply(identity, lambda t: self.bridge.set_speed(t, percent))

    async def async_set_mode(self, identity: str, mode: int) -> None:
        await self._apply(identity, lambda t: self.bridge.set_mode(t, mode))

    async def async_run_schedule(self, identity: str) -> None:
        await self._apply(identity, lambda t: self.bridge.run_schedule(t))
