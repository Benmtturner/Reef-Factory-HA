"""EcoTech (Mobius) device family for Multi Reef.

EcoTech gear (VorTech pumps, Radion lights, …) speaks Bluetooth LE, so it reaches
Home Assistant through a small ESP32 Wi-Fi bridge that exposes a JSON API on the
LAN. This subpackage holds the EcoTech-specific logic — the bridge HTTP client and
its coordinator — while the HA platform entry points (sensor.py, select.py, …) live
at the integration root and dispatch here by device family.

The bridge firmware and wire protocol are documented in the local mobius/ notes.
"""
