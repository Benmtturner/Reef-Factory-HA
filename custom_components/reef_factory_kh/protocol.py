"""Binary protocol codec for the Reef Factory KH Keeper.

Pure functions with no Home Assistant dependencies, so they can be unit-tested
in isolation.

Frame format (both directions):
    [serial\\0][command\\0][subcommand\\0][identifier\\0][payload]
ASCII null-terminated string fields; raw binary payload. Multi-byte integers are
big-endian. Fixed-point values are integer ten-thousandths (÷10000).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, tzinfo

SCALE = 10000

ZERO_SERIAL = "0000000000000000"

MEASUREMENT_STATES = {
    0: "Idle",
    1: "Measuring",
    3: "Cancelling",
    4: "Re-measuring",
}


def status_name(state: int) -> str:
    """Human-readable measurement state."""
    return MEASUREMENT_STATES.get(state, f"Unknown ({state})")

_SETTINGS_HEADER = 17
_RECORD_LEN = 16
_CONFIG_FIRMWARE_LEN = 5


@dataclass(frozen=True)
class Frame:
    """A parsed WebSocket frame."""

    serial: str
    command: str
    subcommand: str
    identifier: str
    payload: bytes


@dataclass(frozen=True)
class DeviceConfig:
    """Result of the get/config handshake."""

    serial: str
    firmware: str


@dataclass(frozen=True)
class KhMeasurement:
    """One row of the device's measurement history."""

    kh_dkh: float
    ph: float
    timestamp: datetime | None
    type: int
    alert: int


@dataclass(frozen=True)
class KhState:
    """Decoded KH Keeper state from a khRefresh/settings frame."""

    reagent_ml: float | None  # remaining reagent, offset 11 (confirmed by change-diff)
    reagent_alert: bool
    interval_code: int
    alert_low_dkh: float | None  # offset 0 (confirmed)
    alert_high_dkh: float | None  # offset 4 (confirmed)
    measurement_state: int  # offset 8 — 0/1/3/4, mirrors status frame
    measurement_progress: int  # offset 9 — percent
    history: tuple[KhMeasurement, ...]

    @property
    def measurement_status(self) -> str:
        return status_name(self.measurement_state)

    @property
    def kh_out_of_range(self) -> bool | None:
        """True if the latest KH is outside the alert band."""
        if self.kh_dkh is None or self.alert_low_dkh is None or self.alert_high_dkh is None:
            return None
        return self.kh_dkh < self.alert_low_dkh or self.kh_dkh > self.alert_high_dkh

    @property
    def latest(self) -> KhMeasurement | None:
        """Most recent measurement (history is newest-first)."""
        return self.history[0] if self.history else None

    @property
    def kh_dkh(self) -> float | None:
        return self.latest.kh_dkh if self.latest else None

    @property
    def ph(self) -> float | None:
        return self.latest.ph if self.latest else None

    @property
    def last_measurement(self) -> datetime | None:
        return self.latest.timestamp if self.latest else None

    @property
    def kh_change_dkh(self) -> float | None:
        """Change in KH from the previous measurement to the latest."""
        if len(self.history) < 2:
            return None
        return round(self.history[0].kh_dkh - self.history[1].kh_dkh, 2)


def _u16(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 2], "big")


def _u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off:off + 4], "big")


def build_frame(
    serial: str,
    command: str,
    subcommand: str = "",
    identifier: str = "",
    payload: bytes = b"",
) -> bytes:
    """Construct an outgoing binary frame."""
    parts = bytearray()
    for field in (serial, command, subcommand, identifier):
        parts += field.encode("ascii") + b"\x00"
    return bytes(parts + payload)


def parse_frame(data: bytes) -> Frame:
    """Parse an incoming binary frame into its fields + payload."""
    fields: list[str] = []
    pos = 0
    for _ in range(4):
        end = data.find(b"\x00", pos)
        if end == -1:
            end = len(data)
        fields.append(data[pos:end].decode("ascii", "replace"))
        pos = end + 1
    return Frame(fields[0], fields[1], fields[2], fields[3], data[pos:])


def decode_config(payload: bytes) -> DeviceConfig:
    """Decode a refresh/config payload: [serial\\0][lang][onboarding][fw×5]."""
    end = payload.find(b"\x00")
    if end == -1:
        end = len(payload)
    serial = payload[:end].decode("ascii", "replace")
    fw_start = end + 3  # skip null + language + onboarding bytes
    firmware = payload[fw_start:fw_start + _CONFIG_FIRMWARE_LEN].decode("ascii", "replace")
    return DeviceConfig(serial=serial, firmware=firmware)


def decode_settings(payload: bytes, tz: tzinfo | None = None) -> KhState:
    """Decode a khRefresh/settings frame.

    Real data is a 17-byte header + N×16-byte history records. Anything past the
    last record is leaked device RAM and must be ignored (firmware bug).
    """
    if len(payload) < _SETTINGS_HEADER:
        raise ValueError(f"settings frame too short: {len(payload)} bytes")

    count = payload[16]
    records: list[KhMeasurement] = []
    off = _SETTINGS_HEADER

    for _ in range(count):
        if off + _RECORD_LEN > len(payload):
            break

        year = _u16(payload, off + 8)
        month = ((payload[off + 10] - 1) % 12) + 1
        day = payload[off + 11]
        hour = payload[off + 12]
        minute = payload[off + 13]
        try:
            ts: datetime | None = datetime(year, month, day, hour, minute, tzinfo=tz)
        except ValueError:
            ts = None

        records.append(
            KhMeasurement(
                kh_dkh=round(_u32(payload, off) / SCALE, 2),
                ph=round(_u32(payload, off + 4) / SCALE, 2),
                timestamp=ts,
                type=payload[off + 14],
                alert=payload[off + 15],
            )
        )
        off += _RECORD_LEN

    return KhState(
        reagent_ml=round(_u32(payload, 11) / SCALE, 1),
        reagent_alert=bool(payload[15]),
        interval_code=payload[10],
        alert_low_dkh=round(_u32(payload, 0) / SCALE, 2),
        alert_high_dkh=round(_u32(payload, 4) / SCALE, 2),
        measurement_state=payload[8],
        measurement_progress=payload[9],
        history=tuple(records),
    )


def decode_status(payload: bytes) -> tuple[int, int]:
    """Decode a khRefresh/status frame into (state, progress%)."""
    state = payload[0] if payload else 0
    progress = payload[1] if len(payload) > 1 else 0
    return state, progress


def encode_reagent(ml: float) -> bytes:
    """Encode a khSet/reagent payload: big-endian u32 of ml × SCALE.

    Confirmed against the device: setting 850 mL produced 8_500_000 on the wire.
    """
    max_ml = 0xFFFFFFFF // SCALE
    value = max(0, min(max_ml, int(round(ml))))
    return (value * SCALE).to_bytes(4, "big")


# ---------------------------------------------------------------------------
# Single-head doser (RFDP) — binary, scale ÷100 (NOT the KH ÷10000).
# Field offsets in dpRefresh/settings confirmed by live change-diff against the
# 360 Smart Reef app; see DP_PROTOCOL.md. Frame tail past ~0x30 is leaked RAM.
# ---------------------------------------------------------------------------

DP_SCALE = 100
DP_DAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")  # bit0..bit6

# dpRefresh/settings — fixed field offsets (big-endian, ÷100 unless noted).
_DP_OFF_CONTAINER = 0x00      # container level, u32
_DP_OFF_CAPACITY = 0x04       # container capacity, u32
_DP_OFF_CAL_DATE = 0x0D       # calibration date [day:u8][mon:u8][year:u16 BE]
_DP_OFF_DAILY_TOTAL = 0x16    # today's scheduled total, u32
_DP_OFF_DOSE_COUNT = 0x24     # number of doses today, u8
_DP_OFF_PER_DOSE = 0x25       # dose #0 volume (= start of timetable), u32
_DP_OFF_TIMETABLE = 0x25      # timetable: count × [vol:u32][time:u16 min][pad:u8]
_DP_TIMETABLE_REC = 7
_DP_OFF_REFILL = 0xDA         # active manual refill: [total:u32][days:u16]
_DP_OFF_HISTORY = 0xE1        # dose history: N × [sched:u32][manual:u32][date:7B]
_DP_HISTORY_REC = 15
_DP_OFF_DAYMASK = 0x23A       # day bitfield: bit0=Sun..bit6=Sat, bit7=enabled
_DP_HISTORY_COUNT = (_DP_OFF_DAYMASK - _DP_OFF_HISTORY) // _DP_HISTORY_REC  # 23
_DP_SETTINGS_MIN = 0x29       # need byte 0x28 for the per-dose u32
_DP_STATUS_STATE = 8          # status state byte: 2 = dosing
_DP_STATE_DOSING = 2


def _dp_date(payload: bytes, off: int, tz: tzinfo | None = None) -> datetime | None:
    """Calibration-style date `[day:u8][mon:u8][year:u16 BE]` → datetime | None."""
    if len(payload) < off + 4:
        return None
    try:
        return datetime(_u16(payload, off + 2), payload[off + 1], payload[off], tzinfo=tz)
    except ValueError:
        return None


def _dp_history_date(payload: bytes, off: int, tz: tzinfo | None = None) -> datetime | None:
    """History-style date `[u16 year][mon][day][h][m][s]` → datetime | None."""
    if len(payload) < off + 7:
        return None
    try:
        return datetime(
            _u16(payload, off), payload[off + 2], payload[off + 3],
            payload[off + 4], payload[off + 5], payload[off + 6], tzinfo=tz,
        )
    except ValueError:
        return None


@dataclass(frozen=True)
class DpDose:
    """One executed-dose history record."""

    volume_ml: float
    manual: bool
    timestamp: datetime | None


@dataclass(frozen=True)
class DpState:
    """Decoded single-head doser state from a dpRefresh/settings frame.

    ``dosing``/``last_dose_ml``/``last_dose_at`` are not in the settings frame;
    the coordinator patches them from status/dose frames. Time-relative values
    (dosed-today, next-dose) are computed by the entities, which have a clock.
    """

    container_ml: float | None
    capacity_ml: float | None
    daily_total_ml: float | None
    dose_count: int
    per_dose_ml: float | None
    day_mask: int = 0
    timetable: tuple[tuple[int, float], ...] = ()  # (minute-of-day, mL)
    history: tuple[DpDose, ...] = ()
    calibration_date: datetime | None = None
    refill_total_ml: float | None = None  # active multi-day manual refill
    refill_days: int = 0
    dosing: bool = False
    last_dose_ml: float | None = None
    last_dose_at: datetime | None = None

    @property
    def reservoir_pct(self) -> float | None:
        """Container fill as a percentage of capacity."""
        if self.container_ml is None or not self.capacity_ml:
            return None
        return round(100 * self.container_ml / self.capacity_ml, 1)

    @property
    def active_days(self) -> tuple[str, ...]:
        """Weekday names the schedule is enabled for."""
        return tuple(DP_DAY_NAMES[b] for b in range(7) if self.day_mask & (1 << b))

    @property
    def daily_schedule_ml(self) -> float:
        """Full daily scheduled volume (sum of the timetable), regardless of today."""
        return round(sum(v for _, v in self.timetable), 2)

    @property
    def time_left_days(self) -> float | None:
        """Days of reservoir left at the full daily schedule rate."""
        daily = self.daily_schedule_ml
        if self.container_ml is None or daily <= 0:
            return None
        return round(self.container_ml / daily, 1)

    def next_dose(self, minute_of_day: int) -> tuple[int, float] | None:
        """Next scheduled (minute, mL) after minute_of_day, wrapping to tomorrow."""
        if not self.timetable:
            return None
        for minute, ml in self.timetable:
            if minute > minute_of_day:
                return (minute, ml)
        return self.timetable[0]


def decode_dp_settings(payload: bytes, tz: tzinfo | None = None) -> DpState:
    """Decode a dpRefresh/settings frame. Deep fields are length-guarded so a
    short/odd frame still yields the header values."""
    if len(payload) < _DP_SETTINGS_MIN:
        raise ValueError(f"dp settings frame too short: {len(payload)} bytes")

    count = payload[_DP_OFF_DOSE_COUNT]

    timetable: list[tuple[int, float]] = []
    off = _DP_OFF_TIMETABLE
    for _ in range(count):
        if off + _DP_TIMETABLE_REC > len(payload):
            break
        timetable.append((_u16(payload, off + 4), round(_u32(payload, off) / DP_SCALE, 2)))
        off += _DP_TIMETABLE_REC

    history: list[DpDose] = []
    for i in range(_DP_HISTORY_COUNT):
        rec = _DP_OFF_HISTORY + i * _DP_HISTORY_REC
        if rec + _DP_HISTORY_REC > len(payload):
            break
        scheduled = _u32(payload, rec) / DP_SCALE
        manual = _u32(payload, rec + 4) / DP_SCALE
        timestamp = _dp_history_date(payload, rec + 8, tz)
        amount = manual if manual > 0 else scheduled
        if amount <= 0 and timestamp is None:
            continue
        history.append(DpDose(round(amount, 2), manual > 0, timestamp))

    day_mask = payload[_DP_OFF_DAYMASK] if len(payload) > _DP_OFF_DAYMASK else 0
    refill_total = (
        round(_u32(payload, _DP_OFF_REFILL) / DP_SCALE, 2)
        if len(payload) >= _DP_OFF_REFILL + 4 else 0.0
    )
    refill_days = (
        _u16(payload, _DP_OFF_REFILL + 4) if len(payload) >= _DP_OFF_REFILL + 6 else 0
    )

    return DpState(
        container_ml=round(_u32(payload, _DP_OFF_CONTAINER) / DP_SCALE, 2),
        capacity_ml=round(_u32(payload, _DP_OFF_CAPACITY) / DP_SCALE, 2),
        daily_total_ml=round(_u32(payload, _DP_OFF_DAILY_TOTAL) / DP_SCALE, 2),
        dose_count=count,
        per_dose_ml=round(_u32(payload, _DP_OFF_PER_DOSE) / DP_SCALE, 2),
        day_mask=day_mask,
        timetable=tuple(timetable),
        history=tuple(history),
        calibration_date=_dp_date(payload, _DP_OFF_CAL_DATE, tz),
        refill_total_ml=refill_total or None,
        refill_days=refill_days,
    )


def decode_dp_status(payload: bytes) -> tuple[float | None, bool]:
    """Decode a dpRefresh/status frame into (live container mL, dosing?)."""
    level = round(_u32(payload, 0) / DP_SCALE, 2) if len(payload) >= 4 else None
    dosing = (
        len(payload) > _DP_STATUS_STATE and payload[_DP_STATUS_STATE] == _DP_STATE_DOSING
    )
    return level, dosing


def decode_dp_dose(payload: bytes) -> float | None:
    """Decode a dpRefresh/dose frame (4 B): the volume just dispensed, mL."""
    if len(payload) < 4:
        return None
    return round(_u32(payload, 0) / DP_SCALE, 2)


# --- Command encoders (payloads for dp* uplink commands) -------------------


def _dp_u32(ml: float) -> bytes:
    return max(0, min(0xFFFFFFFF, int(round(ml * DP_SCALE)))).to_bytes(4, "big")


def encode_dp_container(current_ml: float, capacity_ml: float) -> bytes:
    """dpSet/container: `[current:u32 ÷100][capacity:u32 ÷100][00]`."""
    return _dp_u32(current_ml) + _dp_u32(capacity_ml) + b"\x00"


def encode_dp_manual_refill(amount_ml: float, days: int = 0) -> bytes:
    """dpManualRefill/start: `[00][amount:u32 ÷100][days:u8][00×5]`.

    ``days=0`` doses it all now; ``days=N`` spreads amount over N days.
    """
    return b"\x00" + _dp_u32(amount_ml) + bytes([max(0, min(255, int(days)))]) + b"\x00" * 5


def encode_dp_skip(percent: int) -> bytes:
    """dpSet/skipNext: `[percent:u8][00]`."""
    return bytes([max(0, min(100, int(percent))), 0])


def encode_dp_doses(doses: list[tuple[int, float]], day_mask: int) -> bytes:
    """dpSet/doses: `[count:u8][count × ([value:u32 ÷100][time:u16 min])][daymask:u8][00]`."""
    out = bytearray([len(doses) & 0xFF])
    for minute, ml in doses:
        out += _dp_u32(ml) + int(minute).to_bytes(2, "big")
    out += bytes([day_mask & 0xFF, 0])
    return bytes(out)


def encode_dp_calibration_value(measured_ml: float) -> bytes:
    """dpCalibration/value: `[measured:u32 ÷100][00]`."""
    return _dp_u32(measured_ml) + b"\x00"


def encode_dp_calibration_notification(period_code: int) -> bytes:
    """dpCalibration/notification: `[period:u8][00]`."""
    return bytes([period_code & 0xFF, 0])


def detect_family(serial: str) -> str | None:
    """Return the device-family prefix (RFKH/RFDP) for a serial, or None."""
    upper = serial.upper()
    for family in ("RFKH", "RFDP"):
        if upper.startswith(family):
            return family
    return None
