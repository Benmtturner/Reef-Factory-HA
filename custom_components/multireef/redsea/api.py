"""Async HTTP client + state model for a Red Sea ReefDose (ReefBeat local API).

Plain ``http://<ip>`` on port 80, **no auth**. GET to read, POST/PUT to write,
JSON throughout. The device is an ESP32 with very limited concurrent connections,
so every call is serialised behind a lock and a poll reads its endpoints one at a
time (gentle) — a burst of parallel connections trips a per-source rate-block.

Endpoints (see redsea/REDSEA_PROTOCOL.md):

    GET  /device-info                 -> {hw_model, name, status, hwid}
    GET  /firmware                    -> {version, ...}
    GET  /dashboard                   -> {battery_level, time_error, heads:{N:{...}}}
    GET  /head/{n}/settings           -> per-head schedule/container/supplement/calib
    POST /head/{n}/manual   {manual_dose_scheduled:true, volume:<mL>}
    PUT  /head/{n}/settings <whole edited head object>
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

import aiohttp

from .const import DOSER_HEADS, DOSER_MODELS, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ReefBeatError(Exception):
    """The device was unreachable or returned an error response."""


def _f(value: Any, default: float = 0.0) -> float:
    """Coerce to float, tolerating None / bad values."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    """Coerce to int, tolerating None / bad values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class HeadState:
    """One dosing head, merged from /dashboard + /head/{n}/settings."""

    index: int
    supplement: str  # display label ("Setup head 1" when unconfigured)
    state: str  # "not-setup", "ready", …
    schedule_enabled: bool
    container_ml: float  # reservoir contents
    daily_dose_ml: float  # target volume/day
    daily_doses: int  # number of doses/day
    doses_today: int
    auto_dosed_today_ml: float
    manual_dosed_today_ml: float
    remaining_days: int
    stock_level: str
    recalibration_required: bool
    last_calibrated: int  # epoch seconds (0 = never)
    schedule_type: str  # "single" | "hourly" | "custom" | "timer"
    schedule_mode: str  # "regular" | …
    dose_time_min: int  # single: first dose, minutes since midnight (schedule.time)
    schedule_min: int  # hourly: minute past each hour (schedule.min)
    days: tuple[int, ...]  # active weekdays 1..7
    missed_ml: float
    is_food_head: bool
    slm: bool  # supplement-level monitor enabled

    @property
    def dosed_today_ml(self) -> float:
        """Total dosed today (auto + manual)."""
        return round(self.auto_dosed_today_ml + self.manual_dosed_today_ml, 2)


@dataclass(frozen=True)
class DoserState:
    """Full snapshot of a ReefDose used by the coordinator/entities."""

    name: str
    model: str  # RSDOSE2 / RSDOSE4
    model_name: str  # "ReefDose 2"
    firmware: str
    hwid: str
    heads_nb: int
    battery_level: str  # "low" = RTC cell dying
    time_error: bool
    is_active: bool
    mode: str  # "auto" (dosing) | "off" (heads off) | "maintenance" | …
    dosing_delay: int  # device: seconds waited between heads (dosing_waiting_period)
    stock_alert_days: int  # device: supplement-volume-monitor "number of days"
    heads: dict[int, HeadState]

    @property
    def heads_on(self) -> bool:
        """Whether automatic dosing is enabled (mode != off)."""
        return self.mode != "off"


def _parse_head(index: int, hs: dict[str, Any], dh: dict[str, Any]) -> HeadState:
    """Merge a head's /head/{n}/settings (hs) and /dashboard head entry (dh)."""
    sched = hs.get("schedule") or {}
    supp = hs.get("supplement") or {}
    label = (
        supp.get("display_name")
        or supp.get("name")
        or dh.get("supplement")
        or f"Head {index}"
    )
    missed = dh.get("missed_dose") or {}
    return HeadState(
        index=index,
        supplement=str(label),
        state=str(hs.get("state") or dh.get("state") or "unknown"),
        schedule_enabled=bool(hs.get("schedule_enabled", False)),
        container_ml=_f(hs.get("container_volume")),
        daily_dose_ml=_f(dh.get("daily_dose", sched.get("dd"))),
        daily_doses=_i(dh.get("daily_doses")),
        doses_today=_i(dh.get("doses_today")),
        auto_dosed_today_ml=_f(dh.get("auto_dosed_today")),
        manual_dosed_today_ml=_f(dh.get("manual_dosed_today")),
        remaining_days=_i(dh.get("remaining_days")),
        stock_level=str(dh.get("stock_level") or "unknown"),
        recalibration_required=bool(hs.get("recalibration_required", False)),
        last_calibrated=_i(hs.get("last_calibrated")),
        schedule_type=str(sched.get("type") or "single"),
        schedule_mode=str(sched.get("mode") or "regular"),
        dose_time_min=_i(sched.get("time")),
        schedule_min=_i(sched.get("min")),
        days=tuple(int(d) for d in (sched.get("days") or []) if _i(d)),
        missed_ml=_f(missed.get("missed_volume")),
        is_food_head=bool(hs.get("is_food_head", False)),
        slm=bool(hs.get("slm", False)),
    )


class ReefDoseClient:
    """Client for one ReefDose, addressed by host (IP or hostname)."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._host = host
        self._base = f"http://{host}"
        # These devices service one request at a time reliably; serialise so a
        # poll's reads never overlap (and never race a write).
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    async def _get(self, path: str) -> Any:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with self._lock:
            try:
                async with self._session.get(
                    f"{self._base}{path}", timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                # ValueError = non-JSON body (JSONDecodeError).
                raise ReefBeatError(f"GET {path} failed: {err}") from err

    async def _send(self, method: str, path: str, payload: Any) -> None:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with self._lock:
            try:
                async with self._session.request(
                    method, f"{self._base}{path}", json=payload, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise ReefBeatError(f"{method.upper()} {path} failed: {err}") from err

    # --- reads ---------------------------------------------------------------

    async def device_info(self) -> dict[str, Any]:
        result = await self._get("/device-info")
        return result if isinstance(result, dict) else {}

    async def fetch_state(
        self,
    ) -> tuple[DoserState, dict[int, dict[str, Any]], dict[str, Any]]:
        """Read the device and return (parsed state, raw per-head settings, raw
        device-settings).

        The raw dicts are returned so the coordinator can do read-modify-write PUTs
        (the device expects the whole object back on /head/{n}/settings and
        /device-settings).
        """
        info = await self.device_info()
        model = str(info.get("hw_model") or "RSDOSE2")
        heads_nb = DOSER_HEADS.get(model, 2)

        fw = await self._get("/firmware")
        firmware = str((fw or {}).get("version") or "?") if isinstance(fw, dict) else "?"

        mode_obj = await self._get("/mode")
        mode = str((mode_obj or {}).get("mode") or "auto") if isinstance(mode_obj, dict) else "auto"

        ds = await self._get("/device-settings")
        ds = ds if isinstance(ds, dict) else {}

        dash = await self._get("/dashboard")
        dash = dash if isinstance(dash, dict) else {}
        dash_heads = dash.get("heads") or {}

        raw_heads: dict[int, dict[str, Any]] = {}
        heads: dict[int, HeadState] = {}
        for n in range(1, heads_nb + 1):
            hs = await self._get(f"/head/{n}/settings")
            hs = hs if isinstance(hs, dict) else {}
            raw_heads[n] = hs
            dh = dash_heads.get(str(n)) or {}
            heads[n] = _parse_head(n, hs, dh)

        state = DoserState(
            name=str(info.get("name") or model),
            model=model,
            model_name=DOSER_MODELS.get(model, "ReefDose"),
            firmware=firmware,
            hwid=str(info.get("hwid") or ""),
            heads_nb=heads_nb,
            battery_level=str(dash.get("battery_level") or "unknown"),
            time_error=bool(dash.get("time_error", False)),
            is_active=bool(dash.get("is_active", False)),
            mode=mode,
            dosing_delay=_i(ds.get("dosing_waiting_period")),
            stock_alert_days=_i(ds.get("stock_alert_days")),
            heads=heads,
        )
        return state, raw_heads, ds

    # --- writes --------------------------------------------------------------

    async def manual_dose(self, head: int, volume_ml: float) -> None:
        """Dose ``volume_ml`` now on ``head`` (POST /head/{n}/manual)."""
        await self._send(
            "post",
            f"/head/{head}/manual",
            {"manual_dose_scheduled": True, "volume": volume_ml},
        )

    async def put_head_settings(self, head: int, obj: dict[str, Any]) -> None:
        """Write a full head settings object back (PUT /head/{n}/settings)."""
        await self._send("put", f"/head/{head}/settings", obj)

    async def put_device_settings(self, obj: dict[str, Any]) -> None:
        """Write the full device-settings object back (PUT /device-settings)."""
        await self._send("put", "/device-settings", obj)

    async def set_heads_off(self, off: bool) -> None:
        """Turn all dosing off (POST /off) or back to auto (DELETE /off)."""
        if off:
            await self._send("post", "/off", None)
        else:
            await self._send("delete", "/off", None)

    async def prime(self, head: int, start: bool) -> None:
        """Start/stop priming a head (POST /head/{n}/priming/{start|stop})."""
        await self._send("post", f"/head/{head}/priming/{'start' if start else 'stop'}", None)
