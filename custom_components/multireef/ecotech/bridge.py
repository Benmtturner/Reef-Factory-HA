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

        The MP10 (and others) roll a new random-static MAC on every power-cycle, so
        the serial is the only durable identity. MAC is a fallback for gear that
        never advertises a serial.
        """
        return self.serial or self.mac

    @property
    def target(self) -> str:
        """Query fragment to address this device on the bridge — serial preferred
        (the bridge resolves it to the current address), MAC only as a fallback."""
        return f"serial={self.serial}" if self.serial else f"mac={self.mac}"


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

    async def state(self, target: str) -> DeviceState:
        """Read scene/mode/speed for one device (brief connect-on-demand).

        ``target`` is a query fragment addressing the device — ``serial=…`` (stable,
        preferred) or ``mac=…``. The bridge resolves a serial to the current address.
        """
        d = await self._request("GET", f"/state?{target}")
        if not isinstance(d, dict):
            raise BridgeError(f"/state?{target} returned non-object")
        return DeviceState(
            mac=str(d.get("mac", "")),
            scene=int(d.get("scene", -1)),
            mode=int(d.get("mode", -1)),
            mode_name=str(d.get("modeName", "?")),
            speed=float(d.get("speed", -1)),
            speed_raw=int(d.get("speedRaw", -1)),
            live=int(d.get("live", -1)),
            ok=bool(d.get("ok", False)),
        )

    async def set_scene(self, target: str, scene: int) -> None:
        await self._request("POST", f"/scene?{target}&value={int(scene)}")

    async def set_speed(self, target: str, percent: int) -> None:
        """Set + PERSIST wave speed (the bridge does preview 0x197 + commit 0x1F4)."""
        await self._request("POST", f"/speed?{target}&value={int(percent)}")

    async def set_mode(self, target: str, mode: int) -> None:
        """Set + PERSIST wave mode (preview + commit)."""
        await self._request("POST", f"/mode?{target}&value={int(mode)}")

    async def run_schedule(self, target: str) -> None:
        await self._request("POST", f"/run?{target}")

    async def upload_firmware(self, data: bytes) -> None:
        """OTA a new firmware image to the bridge (multipart POST /update).

        The bridge flashes it and reboots, so this returns once the upload is
        accepted; the new version shows up on the next poll of /health.
        """
        form = aiohttp.FormData()
        form.add_field(
            "firmware", data, filename="mobius_bridge.bin",
            content_type="application/octet-stream",
        )
        timeout = aiohttp.ClientTimeout(total=120)  # a ~1 MB image over Wi-Fi
        async with self._lock:
            try:
                async with self._session.post(
                    f"{self._base}/update", data=form, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                raise BridgeError(f"firmware upload failed: {err}") from err
