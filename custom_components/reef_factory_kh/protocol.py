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
