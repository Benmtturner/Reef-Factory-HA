"""Constants for the Red Sea (ReefBeat) family.

Mappings decoded from a live RSDOSE2 (fw 3.0.0) + the MIT ha-reefbeat-component
source; see the local redsea/REDSEA_PROTOCOL.md for how these were derived.
"""

from __future__ import annotations

MANUFACTURER = "Red Sea"

# Model IDs advertised in /device-info -> hw_model.
MODEL_DOSE2 = "RSDOSE2"
MODEL_DOSE4 = "RSDOSE4"

# Head count per doser model, and a friendly name.
DOSER_HEADS: dict[str, int] = {MODEL_DOSE2: 2, MODEL_DOSE4: 4}
DOSER_MODELS: dict[str, str] = {MODEL_DOSE2: "ReefDose 2", MODEL_DOSE4: "ReefDose 4"}

# Auto top-off. The model string really is "RSATO+" (literal plus) in /device-info.
MODEL_ATO = "RSATO+"
ATO_MODELS: dict[str, str] = {MODEL_ATO: "ReefATO+"}

# Everything the redsea family can set up, for discovery + config-flow labels.
SUPPORTED_MODELS: dict[str, str] = {**DOSER_MODELS, **ATO_MODELS}

# Every ReefBeat model-ID prefix, used to recognise devices during a discovery
# scan. Only dosers are controllable so far; the rest are listed so a scan can
# still report them (future families extend this).
KNOWN_MODEL_PREFIXES: tuple[str, ...] = (
    "RSDOSE",
    "RSLED",
    "RSMAT",
    "RSATO",
    "RSRUN",
    "RSWAVE",
    "RSPOWER",
    "RSCONTROL",
)

# --- HTTP ---
# Plain http://<ip>:80, no auth. A call can take a couple of seconds on these
# ESP32 devices; give it headroom but not so long a dead host stalls a scan.
REQUEST_TIMEOUT = 10  # seconds per call

# Background poll cadence. A poll reads a handful of endpoints; the client
# serialises them (one at a time) because these devices rate-block bursts of
# concurrent connections — so keep it gentle and infrequent.
POLL_INTERVAL = 120  # seconds

# Config-flow subnet scan. Red Sea devices trip a per-source rate-block when hit
# by a heavy parallel sweep, so the scan uses modest concurrency + a short
# per-host timeout, a single pass. Manual IP entry is the reliable fallback.
SCAN_TIMEOUT = 1.5  # seconds per host
SCAN_CONCURRENCY = 12  # simultaneous probes (single sweep)

# Default manual-dose volume offered per head (mL) until the user changes it.
DEFAULT_MANUAL_DOSE_ML = 5.0
# Bounds for the manual-dose / container number entities (mL).
MANUAL_DOSE_MAX_ML = 500.0
CONTAINER_MAX_ML = 5000.0
# Daily dose target per head (mL/day).
DAILY_DOSE_MAX_ML = 1000.0
# Device dosing delay (seconds waited between dosing each head).
DOSING_DELAY_MAX_S = 600
# Supplement-volume-monitor "number of days" alert threshold.
STOCK_DAYS_MAX = 90

UNIT_ML = "mL"

# schedule.days uses ISO-ish weekday ints 1..7. Map to labels for a sensor.
WEEKDAYS: dict[int, str] = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}
