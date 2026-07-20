"""EcoTech (Mobius) family constants — mappings decoded from the live MP10.

See the local mobius/MOBIUS_PROTOCOL.md for how these were reverse-engineered.
"""

from __future__ import annotations

MANUFACTURER = "EcoTech Marine"

DEFAULT_BRIDGE_HOST = "multireef.local"
# Background poll cadence. A poll briefly connects to each pump over BLE, so keep it
# gentle — every 5 min — and rely on the Refresh button for an immediate read.
POLL_INTERVAL = 300  # seconds (5 min)

# Version of the bridge firmware bundled at firmware/mobius_bridge.bin. The update
# entity offers this to any bridge running an older fw (compared to its /health).
# Keep in lockstep with FW_VERSION in mobius/mobius_bridge/mobius_bridge.ino.
BRIDGE_FW_VERSION = "0.1.7"

# Advert manufacturer-data type byte → model. Only 0x0B is confirmed so far; the
# rest of the user's fleet is unmapped (ID them by reading the device-name attr).
TYPE_MP10 = 0x0B
MODEL_NAMES: dict[int, str] = {TYPE_MP10: "VorTech MP10"}

# Devices we currently expose live controls for (poll /state + build entities).
# Others still appear in discovery but aren't polled until their model is added.
CONTROLLABLE_TYPES: frozenset[int] = frozenset({TYPE_MP10})

# Wave program mode enum (0x197 value offset 24). 1/3 confirmed live; extend as
# more are mapped in the app-change-then-reread decode.
WAVE_MODES: dict[int, str] = {1: "Constant", 3: "ReefCrest"}

# CurrentScene (attr 0x191) built-ins. 0 = normal schedule, 1 = Feed, …
SCENES: dict[int, str] = {
    0: "Schedule",
    1: "Feed",
    2: "Battery Backup",
    3: "All Off",
    4: "Colour Cycle",
    5: "Disco",
    6: "Thunderstorm",
    7: "Cloud Cover",
    8: "All On",
    9: "All 50%",
}

SCENE_SCHEDULE = 0
