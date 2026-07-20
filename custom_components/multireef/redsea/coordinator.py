"""Coordinator + discovery for a Red Sea ReefDose.

One config entry == one doser. A normal polling DataUpdateCoordinator reads the
device's endpoints (gently, one at a time) into a DoserState. Writes read-modify-
write the cached raw head object and PUT it back, then request a refresh.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

import aiohttp
from homeassistant.components import network
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import (
    CONF_REDSEA_HWID,
    CONF_REDSEA_MODEL,
)
from .api import DoserState, ReefBeatError, ReefDoseClient
from .const import (
    DEFAULT_MANUAL_DOSE_ML,
    DOSER_HEADS,
    DOSER_MODELS,
    POLL_INTERVAL,
    REQUEST_TIMEOUT,
    SCAN_CONCURRENCY,
    SCAN_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


async def async_probe_doser(hass: HomeAssistant, host: str) -> dict[str, Any]:
    """Read /device-info for one host and return it if it's a ReefDose.

    Raises on connection failure. Returns the device-info dict (caller checks the
    model). Used by the config flow's manual-entry path.
    """
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    try:
        async with session.get(f"http://{host}/device-info", timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        # ValueError covers a non-JSON body (JSONDecodeError) — not a ReefDose.
        raise ReefBeatError(f"probe {host} failed: {err}") from err
    return data if isinstance(data, dict) else {}


async def _probe_quiet(
    session: aiohttp.ClientSession, host: str, timeout: float
) -> dict[str, Any] | None:
    """Probe one host for /device-info, returning it or None (never raises).

    Scans hit arbitrary hosts (routers, other HTTP devices) that may answer 200
    with non-JSON — so swallow *any* failure (incl. JSONDecodeError) and treat it
    as "not a ReefDose here".
    """
    try:
        async with asyncio.timeout(timeout):
            async with session.get(f"http://{host}/device-info") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
    except Exception:  # noqa: BLE001 — any failure just means "no doser at this IP"
        return None
    return data if isinstance(data, dict) else None


async def async_scan_dosers(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Scan the HA host's /24 for ReefDose devices.

    Returns {ip: device_info} for RSDOSE* devices. Uses modest concurrency + a
    short timeout in a single pass — a heavy parallel sweep trips these devices'
    rate-block, so manual IP entry stays the reliable fallback.
    """
    try:
        local_ip = await network.async_get_source_ip(hass, target_ip="8.8.8.8")
    except (RuntimeError, OSError):
        return {}
    if not local_ip or local_ip.count(".") != 3:
        return {}

    base = local_ip.rsplit(".", 1)[0]
    session = async_get_clientsession(hass)
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
    found: dict[str, dict[str, Any]] = {}

    async def _scan_one(host: str) -> None:
        async with semaphore:
            info = await _probe_quiet(session, host, SCAN_TIMEOUT)
        if info and str(info.get("hw_model") or "") in DOSER_HEADS:
            found[host] = info

    # return_exceptions so one bad host can never abort the whole scan.
    await asyncio.gather(
        *(_scan_one(f"{base}.{i}") for i in range(1, 255)), return_exceptions=True
    )
    return found


class RedSeaDoserCoordinator(DataUpdateCoordinator[DoserState]):
    """Polls one ReefDose over its local HTTP API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.host: str = entry.data[CONF_HOST]
        super().__init__(
            hass,
            _LOGGER,
            name=f"redsea_doser_{self.host}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self.entry = entry
        self.hwid: str = entry.data.get(CONF_REDSEA_HWID, "")
        self.model: str = entry.data.get(CONF_REDSEA_MODEL, "RSDOSE2")
        self.model_name: str = DOSER_MODELS.get(self.model, "ReefDose")
        self.firmware: str = "?"
        self._client = ReefDoseClient(async_get_clientsession(hass), self.host)
        self._raw_heads: dict[int, dict[str, Any]] = {}
        self._raw_device_settings: dict[str, Any] = {}
        # Per-head manual-dose setpoint (mL), driven by a Number entity and read by
        # the "Dose Now" button — a local value, not pushed to the device.
        self.manual_dose_ml: dict[int, float] = {}

    @property
    def heads_nb(self) -> int:
        return self.data.heads_nb if self.data else DOSER_HEADS.get(self.model, 2)

    async def _async_update_data(self) -> DoserState:
        try:
            state, raw_heads, raw_ds = await self._client.fetch_state()
        except ReefBeatError as err:
            raise UpdateFailed(f"ReefDose {self.host} unreachable: {err}") from err
        self._raw_heads = raw_heads
        self._raw_device_settings = raw_ds
        self.firmware = state.firmware
        if state.hwid:
            self.hwid = state.hwid
        return state

    # --- manual-dose setpoint (local) ---------------------------------------

    def get_manual_dose(self, head: int) -> float:
        return self.manual_dose_ml.get(head, DEFAULT_MANUAL_DOSE_ML)

    def set_manual_dose(self, head: int, ml: float) -> None:
        self.manual_dose_ml[head] = ml

    async def _write(self, awaitable) -> None:
        """Run a device write; turn a device error into a clean HA error dialog
        (e.g. "cannot have multiple manual doses for same head")."""
        try:
            await awaitable
        except ReefBeatError as err:
            raise HomeAssistantError(str(err)) from err

    # --- device writes -------------------------------------------------------

    async def async_manual_dose(self, head: int, volume_ml: float | None = None) -> None:
        """Dose now on ``head`` (defaults to the head's manual setpoint)."""
        ml = self.get_manual_dose(head) if volume_ml is None else volume_ml
        await self._write(self._client.manual_dose(head, ml))
        await self.async_request_refresh()

    async def _patch_head(self, head: int, **changes: Any) -> None:
        """Read-modify-write a head's settings object and PUT it back."""
        raw = self._raw_heads.get(head)
        if not raw:
            _LOGGER.warning("no cached settings for head %s; skipping write", head)
            return
        updated = {**raw, **changes}
        await self._write(self._client.put_head_settings(head, updated))
        self._raw_heads[head] = updated
        await self.async_request_refresh()

    async def _patch_head_schedule(self, head: int, **changes: Any) -> None:
        """Read-modify-write a head's nested ``schedule`` object."""
        raw = self._raw_heads.get(head)
        if not raw:
            _LOGGER.warning("no cached settings for head %s; skipping write", head)
            return
        schedule = {**(raw.get("schedule") or {}), **changes}
        updated = {**raw, "schedule": schedule}
        await self._write(self._client.put_head_settings(head, updated))
        self._raw_heads[head] = updated
        await self.async_request_refresh()

    async def _patch_device_settings(self, **changes: Any) -> None:
        """Read-modify-write the device-settings object."""
        raw = self._raw_device_settings
        if not raw:
            _LOGGER.warning("no cached device-settings; skipping write")
            return
        updated = {**raw, **changes}
        await self._write(self._client.put_device_settings(updated))
        self._raw_device_settings = updated
        await self.async_request_refresh()

    async def async_set_container(self, head: int, volume_ml: float) -> None:
        """Set the reservoir contents (mL) for a head."""
        await self._patch_head(head, container_volume=volume_ml)

    async def async_set_schedule_enabled(self, head: int, enabled: bool) -> None:
        """Enable/disable the automatic schedule for a head."""
        await self._patch_head(head, schedule_enabled=enabled)

    async def async_set_heads_on(self, on: bool) -> None:
        """Turn automatic dosing on (auto) or off (all heads off)."""
        await self._write(self._client.set_heads_off(not on))
        await self.async_request_refresh()

    async def async_set_daily_dose(self, head: int, ml: float) -> None:
        """Set a head's dose-per-day target (schedule.dd)."""
        await self._patch_head_schedule(head, dd=ml)

    async def async_set_priming(self, head: int, start: bool) -> None:
        """Start/stop priming a head's dosing tube."""
        await self._write(self._client.prime(head, start))
        await self.async_request_refresh()

    async def async_set_food_head(self, head: int, enabled: bool) -> None:
        """Mark/unmark a head as the feed-mode head."""
        await self._patch_head(head, is_food_head=enabled)

    async def async_set_slm(self, head: int, enabled: bool) -> None:
        """Enable/disable the supplement-level monitor for a head."""
        await self._patch_head(head, slm=enabled)

    async def async_set_dosing_delay(self, seconds: int) -> None:
        """Set the device dosing delay (seconds waited between heads)."""
        await self._patch_device_settings(dosing_waiting_period=int(seconds))

    async def async_set_stock_days(self, days: int) -> None:
        """Set the supplement-volume-monitor 'number of days' threshold."""
        await self._patch_device_settings(stock_alert_days=int(days))
