"""Async HTTP client for a Multi Reef EcoTech bridge (ESP32 ↔ Mobius BLE gateway).

The bridge exposes a tiny JSON API over the LAN (see mobius/mobius_bridge firmware):

    GET  /health                     → bridge status
    GET  /devices                    → [{mac,type,model,serial,rssi}] (BLE advert scan)
    GET  /state?mac=..               → {scene,mode,modeName,speed,speedRaw,live}
    POST /scene|/speed|/mode?mac=&value=
    POST /run?mac=..                 → resume schedule

Every call drives a connect-on-demand BLE session on the ESP32, so requests to a
given bridge are serialised here with a lock — the bridge holds one BLE client at a
time and cannot service overlapping requests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

# A connect-on-demand BLE round-trip (scan/connect/read/disconnect) can take a few
# seconds; give each request generous headroom before giving up.
REQUEST_TIMEOUT = 20


class BridgeError(Exception):
    """The bridge was unreachable or returned an error response."""


@dataclass(frozen=True)
class BridgeDevice:
    """A Mobius device as seen in the bridge's advert scan (/devices)."""

    mac: str
    type: int
    model: str
    serial: str
    rssi: int

    @property
    def identity(self) -> str:
        """Stable id: serial when advertised, else the MAC.

        Public-address gear (MP10, Radion cluster) has a stable MAC; some units use
        rotating random addresses, so their serial is the only durable identity.
        """
        return self.serial or self.mac


@dataclass(frozen=True)
class DeviceState:
    """Live state of one Mobius device (/state)."""

    mac: str
    scene: int
    mode: int
    mode_name: str
    speed: float  # percent (0–100), -1 if unknown
    speed_raw: int
    live: int
    ok: bool


class MobiusBridge:
    """Client for a single bridge, addressed by host (IP or ``multireef.local``)."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self._session = session
        self._host = host
        self._base = f"http://{host}"
        self._lock = asyncio.Lock()  # the bridge services one BLE op at a time

    @property
    def host(self) -> str:
        return self._host

    async def _request(self, method: str, path: str) -> dict | list:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with self._lock:
            try:
                async with self._session.request(
                    method, f"{self._base}{path}", timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise BridgeError(f"{method} {path} failed: {err}") from err

    async def health(self) -> dict:
        """Bridge status: fw version, ip, rssi, free heap, device count."""
        result = await self._request("GET", "/health")
        return result if isinstance(result, dict) else {}

    async def devices(self) -> list[BridgeDevice]:
        """Scan for Mobius devices in range and return what the bridge can see."""
        result = await self._request("GET", "/devices")
        rows = result if isinstance(result, list) else []
        return [
            BridgeDevice(
                mac=str(d.get("mac", "")),
                type=int(d.get("type", 0)),
                model=str(d.get("model", "Unknown")),
                serial=str(d.get("serial", "")),
                rssi=int(d.get("rssi", 0)),
            )
            for d in rows
        ]

    async def state(self, mac: str) -> DeviceState:
        """Read scene/mode/speed for one device (brief connect-on-demand)."""
        d = await self._request("GET", f"/state?mac={mac}")
        if not isinstance(d, dict):
            raise BridgeError(f"/state?mac={mac} returned non-object")
        return DeviceState(
            mac=str(d.get("mac", mac)),
            scene=int(d.get("scene", -1)),
            mode=int(d.get("mode", -1)),
            mode_name=str(d.get("modeName", "?")),
            speed=float(d.get("speed", -1)),
            speed_raw=int(d.get("speedRaw", -1)),
            live=int(d.get("live", -1)),
            ok=bool(d.get("ok", False)),
        )

    async def set_scene(self, mac: str, scene: int) -> None:
        await self._request("POST", f"/scene?mac={mac}&value={int(scene)}")

    async def set_speed(self, mac: str, percent: int) -> None:
        await self._request("POST", f"/speed?mac={mac}&value={int(percent)}")

    async def set_mode(self, mac: str, mode: int) -> None:
        await self._request("POST", f"/mode?mac={mac}&value={int(mode)}")

    async def run_schedule(self, mac: str) -> None:
        await self._request("POST", f"/run?mac={mac}")
