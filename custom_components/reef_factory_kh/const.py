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
MODEL = "KH Keeper"
DEVICE_FAMILY = "RFKH"

CONF_SERIAL = "serial_number"
CONF_FIRMWARE = "firmware_version"

# Options
CONF_LOG_FRAMES = "log_frames"  # diagnostic: log every distinct frame to the HA log

UNIT_DKH = "dKH"
