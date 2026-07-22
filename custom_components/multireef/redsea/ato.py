"""Red Sea ReefATO+ (RSATO+) — state model, client and coordinator.

Read-only for now: the priority is monitoring (temperature above all), so a poll
reads four GET endpoints and no writes are exposed yet. Captured live from an
RSATO+ on fw 1.7.5 / framework 4.3.2 — see redsea/REDSEA_PROTOCOL.md.

    GET /device-info    {hw_model:"RSATO+", name, hwid, hw_revision}
    GET /firmware       {version, ...}
    GET /dashboard      fills/volume counters, pump + water level, leak_sensor{},
                        ato_sensor{current_read: temperature °C, ...}
    GET /configuration  temperature ranges/offset, auto_fill, leak + buzzer config
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..const import CONF_REDSEA_HWID, CONF_REDSEA_MODEL
from .api import ReefBeatClient, ReefBeatError, _f, _i
from .const import ATO_MODELS, MODEL_ATO, POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AtoState:
    """Snapshot of a ReefATO+, merged from /dashboard + /configuration."""

    name: str
    model: str
    model_name: str
    firmware: str
    hwid: str
    mode: str  # "auto" | ...
    auto_fill: bool

    # Temperature (probe is optional and can be disabled in the app).
    temperature: float | None  # °C, offset already applied by the device
    temp_enabled: bool
    temp_probe_connected: bool
    temp_desired_low: float
    temp_desired_high: float
    temp_acceptable_low: float
    temp_acceptable_high: float

    # Water level / pump.
    water_level: str  # e.g. "desired_level_1"
    sensor_level: str  # ato_sensor.current_level, e.g. "desired"
    pump_state: str
    is_pump_on: bool
    last_pump_on_cause: str

    # Fill statistics (volumes in mL, straight from the device).
    today_fills: int
    today_volume_ml: float
    daily_fills_average: int
    daily_volume_average_ml: float
    total_fills: int
    total_volume_ml: float
    last_fill_ts: int  # epoch seconds (0 = never)

    # Reservoir monitor (null unless an RVM reservoir is configured).
    volume_left_ml: float | None
    days_till_empty: int | None

    # Leak sensor.
    leak_connected: bool
    leak_status: str  # "dry" | ...
    leak_detected: bool

    # Health.
    ato_sensor_connected: bool
    ato_sensor_error: bool
    check_sensor: bool
    is_calibrated: bool


def _parse_ato(
    info: dict[str, Any],
    firmware: str,
    dash: dict[str, Any],
    conf: dict[str, Any],
) -> AtoState:
    ato = dash.get("ato_sensor") or {}
    leak = dash.get("leak_sensor") or {}
    temp_conf = conf.get("temperature") or {}

    temp_enabled = bool(ato.get("is_temp_enabled", temp_conf.get("enabled", False)))
    probe_connected = str(ato.get("temperature_probe_status") or "") == "connected"
    raw_temp = ato.get("current_read")
    temperature = (
        _f(raw_temp) if temp_enabled and probe_connected and raw_temp is not None else None
    )

    volume_left = dash.get("volume_left")
    days_left = dash.get("days_till_empty")

    return AtoState(
        name=str(info.get("name") or MODEL_ATO),
        model=str(info.get("hw_model") or MODEL_ATO),
        model_name=ATO_MODELS.get(str(info.get("hw_model") or ""), "ReefATO+"),
        firmware=firmware,
        hwid=str(info.get("hwid") or ""),
        mode=str(dash.get("mode") or "auto"),
        auto_fill=bool(conf.get("auto_fill", True)),
        temperature=temperature,
        temp_enabled=temp_enabled,
        temp_probe_connected=probe_connected,
        temp_desired_low=_f(temp_conf.get("desired_range_low")),
        temp_desired_high=_f(temp_conf.get("desired_range_high")),
        temp_acceptable_low=_f(temp_conf.get("acceptable_range_low")),
        temp_acceptable_high=_f(temp_conf.get("acceptable_range_high")),
        water_level=str(dash.get("water_level") or "unknown"),
        sensor_level=str(ato.get("current_level") or "unknown"),
        pump_state=str(dash.get("pump_state") or "unknown"),
        is_pump_on=bool(dash.get("is_pump_on", False)),
        last_pump_on_cause=str(dash.get("last_pump_on_cause") or ""),
        today_fills=_i(dash.get("today_fills")),
        today_volume_ml=_f(dash.get("today_volume_usage")),
        daily_fills_average=_i(dash.get("daily_fills_average")),
        daily_volume_average_ml=_f(dash.get("daily_volume_average")),
        total_fills=_i(dash.get("total_fills")),
        total_volume_ml=_f(dash.get("total_volume_usage")),
        last_fill_ts=_i(dash.get("last_fill_date")),
        volume_left_ml=_f(volume_left) if volume_left is not None else None,
        days_till_empty=_i(days_left) if days_left is not None else None,
        leak_connected=bool(leak.get("connected", False)),
        leak_status=str(leak.get("status") or "unknown"),
        leak_detected=bool(leak.get("connected")) and str(leak.get("status")) != "dry",
        ato_sensor_connected=bool(ato.get("connected", False)),
        ato_sensor_error=bool(ato.get("is_sensor_error", False)),
        check_sensor=bool(dash.get("check_sensor", False)),
        is_calibrated=bool(ato.get("is_calibrated", True)),
    )


class ReefAtoClient(ReefBeatClient):
    """Client for one ReefATO+."""

    async def fetch_state(self) -> AtoState:
        info = await self.device_info()

        fw = await self._get("/firmware")
        firmware = str((fw or {}).get("version") or "?") if isinstance(fw, dict) else "?"

        dash = await self._get("/dashboard")
        dash = dash if isinstance(dash, dict) else {}

        conf = await self._get("/configuration")
        conf = conf if isinstance(conf, dict) else {}

        return _parse_ato(info, firmware, dash, conf)


class RedSeaAtoCoordinator(DataUpdateCoordinator[AtoState]):
    """Polls one ReefATO+ over its local HTTP API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.host: str = entry.data[CONF_HOST]
        super().__init__(
            hass,
            _LOGGER,
            name=f"redsea_ato_{self.host}",
            update_interval=timedelta(seconds=POLL_INTERVAL),
        )
        self.entry = entry
        self.hwid: str = entry.data.get(CONF_REDSEA_HWID, "")
        self.model: str = entry.data.get(CONF_REDSEA_MODEL, MODEL_ATO)
        self.model_name: str = ATO_MODELS.get(self.model, "ReefATO+")
        self.firmware: str = "?"
        self._client = ReefAtoClient(async_get_clientsession(hass), self.host)

    async def _async_update_data(self) -> AtoState:
        try:
            state = await self._client.fetch_state()
        except ReefBeatError as err:
            raise UpdateFailed(f"ReefATO+ {self.host} unreachable: {err}") from err
        self.firmware = state.firmware
        if state.hwid:
            self.hwid = state.hwid
        return state
