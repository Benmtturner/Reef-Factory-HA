"""Red Sea (ReefBeat) device family for Multi Reef.

Red Sea gear (ReefDose dosers, ReefLED lights, ReefWave pumps, ReefMat, ReefATO+,
ReefRun) is Wi-Fi and exposes a plain local HTTP/JSON API — the ReefBeat app talks
to each device directly over the LAN. So, unlike the EcoTech family (Bluetooth LE
via an ESP32 bridge), Red Sea needs **no bridge**: each device is polled directly
by an HTTP DataUpdateCoordinator, structurally like the Reef Factory doser.

This subpackage holds the Red Sea-specific logic (HTTP client, coordinator, entity
bases). The HA platform entry points (sensor.py, number.py, …) live at the
integration root and dispatch here by coordinator type. The reverse-engineered API
is documented in the local redsea/REDSEA_PROTOCOL.md notes.

Only the ReefDose doser is wired up for now; the rest of the fleet is recognised by
discovery and can be added later on the same client.
"""
