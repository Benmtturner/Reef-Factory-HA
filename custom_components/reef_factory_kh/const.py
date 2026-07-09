"""Constants for the Reef Factory KH Keeper integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "reef_factory_kh"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
]

# LAN WebSocket transport.
WS_PATH = "controler"  # single-l typo is hardcoded in the device firmware
WS_SUBPROTOCOL = "arduino"
DEVICE_PORT = 80

# Fixed-point scale for all telemetry values (÷10000 on decode). Confirmed by capture.
SCALE = 10000

CONNECT_TIMEOUT = 10  # seconds
PING_INTERVAL = 30  # seconds — app-level ping/ping keepalive
RECONNECT_MIN = 5
RECONNECT_MAX = 30

# Config-flow subnet scan
SCAN_TIMEOUT = 1.5  # seconds per host
SCAN_CONCURRENCY = 60  # simultaneous probes

MANUFACTURER = "Reef Factory"

# Device families this integration supports, keyed by serial prefix.
FAMILY_KH = "RFKH"
FAMILY_DP = "RFDP"
SUPPORTED_FAMILIES = (FAMILY_KH, FAMILY_DP)
MODELS = {FAMILY_KH: "KH Keeper", FAMILY_DP: "Doser"}

# Back-compat aliases (KH was the original single-device integration).
MODEL = MODELS[FAMILY_KH]
DEVICE_FAMILY = FAMILY_KH

CONF_SERIAL = "serial_number"
CONF_FIRMWARE = "firmware_version"
CONF_MAC = "mac"
CONF_FAMILY = "family"

PONG_TIMEOUT = 10  # seconds — drop the connection if a ping gets no response

# Options
CONF_LOG_FRAMES = "log_frames"  # diagnostic: log every distinct frame to the HA log

UNIT_DKH = "dKH"
UNIT_ML = "mL"
