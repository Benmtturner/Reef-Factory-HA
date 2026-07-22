"""Constants for the Reef Factory KH Keeper integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "multireef"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SELECT,  # KH Keeper measurement interval
]

# EcoTech bridge entries use a different platform set: selects for scene + wave
# mode, a number for speed, sensors for the bridge hub + per-device signal, and
# an update entity for OTA bridge firmware.
ECOTECH_PLATFORMS: list[Platform] = [
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.UPDATE,
    Platform.BUTTON,
]

# Red Sea (ReefBeat) devices poll over local HTTP (no bridge). A ReefDose exposes
# per-head sensors, numbers (manual dose + container), a Dose-Now button, and a
# schedule-enable switch.
REDSEA_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SWITCH,
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

# Config-entry kinds — this umbrella now hosts more than Reef Factory. The
# original RF-device entries carry no marker (treated as a device); EcoTech
# bridge entries set CONF_ENTRY_TYPE so __init__/config-flow can branch.
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_ECOTECH_BRIDGE = "ecotech_bridge"
CONF_BRIDGE_HOST = "bridge_host"

# Red Sea (ReefBeat) device entries — one config entry per device (a ReefDose for
# now). CONF_HOST holds the IP; hwid/model are stored for identity + head count.
ENTRY_TYPE_REDSEA_DOSER = "redsea_doser"
CONF_REDSEA_HWID = "redsea_hwid"
CONF_REDSEA_MODEL = "redsea_model"

PONG_TIMEOUT = 10  # seconds — drop the connection if a ping gets no response

# Options
CONF_LOG_FRAMES = "log_frames"  # diagnostic: log every distinct frame to the HA log

UNIT_DKH = "dKH"
UNIT_ML = "mL"
