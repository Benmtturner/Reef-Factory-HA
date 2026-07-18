"""WebSocket connection manager for the Reef Factory KH Keeper.

Push-based (`local_push`): a background task holds a LAN WebSocket open, runs the
device handshake, joins the KH stream, and feeds decoded state into a
DataUpdateCoordinator. Entities update via the coordinator; there is no polling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from homeassistant.components import network

try:
    from getmac import get_mac_address
except ImportError:  # getmac ships with HA's dhcp component; degrade gracefully
    get_mac_address = None

from .const import (
    CONF_FAMILY,
    CONF_FIRMWARE,
    CONF_LOG_FRAMES,
    CONF_MAC,
    CONF_SERIAL,
    CONNECT_TIMEOUT,
    DOMAIN,
    FAMILY_DP,
    FAMILY_KH,
    MODELS,
    PING_INTERVAL,
    PONG_TIMEOUT,
    RECONNECT_MAX,
    RECONNECT_MIN,
    SCAN_CONCURRENCY,
    SCAN_TIMEOUT,
    SUPPORTED_FAMILIES,
    WS_PATH,
    WS_SUBPROTOCOL,
)
from .protocol import (
    ZERO_SERIAL,
    DeviceConfig,
    DpState,
    KhState,
    build_frame,
    decode_config,
    decode_dp_dose,
    decode_dp_settings,
    decode_dp_status,
    decode_settings,
    decode_status,
    detect_family,
    encode_dp_calibration_notification,
    encode_dp_calibration_value,
    encode_dp_container,
    encode_dp_doses,
    encode_dp_manual_refill,
    encode_dp_skip,
    encode_reagent,
    parse_frame,
)

_LOGGER = logging.getLogger(__name__)

# How often to pull a fresh doser settings frame so HA reflects edits made in the
# RF app or on the device. The doser streams status/dose events live but does not
# reliably push *settings* changes (schedule, container level, calibration), so we
# reconcile on a timer. One small read per cycle — the device already streams
# these frames unprompted, so it is far gentler than a post-write burst.
DP_POLL_INTERVAL = 30
# After a container write the device can bounce (rebooting to persist the value);
# hold off other commands this long so we don't hit it mid-reboot and crash it.
DP_WRITE_COOLDOWN = 6
# A dose is a device-pushed event; pull fresh settings this soon after so today's
# total / history reflect it quickly (the 30 s poll would otherwise be the lag).
DP_DOSE_REFRESH_DELAY = 2


def _describe(frame) -> str:
    """Best-effort one-line decode of a frame for the diagnostic log."""
    p = frame.payload
    try:
        if frame.command == "khRefresh":
            if frame.subcommand == "pH" and len(p) >= 4:
                return f"pH={int.from_bytes(p[0:4], 'big') / 10000:.2f}"
            if frame.subcommand == "status" and len(p) >= 2:
                return f"state={p[0]} progress={p[1]}%"
            if frame.subcommand in ("calibration", "circuit") and len(p) >= 2:
                return f"countdown={p[0]} circuit={p[1]}"
            if frame.subcommand == "settings" and len(p) >= 17:
                return (
                    f"interval={p[10]} reagent_alert={p[15]} records={p[16]} "
                    f"hdr0={int.from_bytes(p[0:4], 'big') / 10000} "
                    f"hdr4={int.from_bytes(p[4:8], 'big') / 10000}"
                )
    except (IndexError, ValueError):
        pass
    return ""


async def async_probe(hass: HomeAssistant, host: str) -> DeviceConfig:
    """Briefly connect to a device and return its serial + firmware.

    Used by the config flow. Raises on any connection problem.
    """
    session = async_get_clientsession(hass)
    url = f"ws://{host}/{WS_PATH}"

    async with asyncio.timeout(CONNECT_TIMEOUT):
        async with session.ws_connect(url, protocols=[WS_SUBPROTOCOL]) as ws:
            await ws.send_bytes(build_frame(ZERO_SERIAL, "get", "config"))
            async for msg in ws:
                if msg.type is not aiohttp.WSMsgType.BINARY:
                    continue
                frame = parse_frame(msg.data)
                if frame.command == "refresh" and frame.subcommand == "config":
                    return decode_config(frame.payload)

    raise ConnectionError("no config response from device")


async def _probe_quiet(
    session: aiohttp.ClientSession, ip: str, timeout: float
) -> DeviceConfig | None:
    """Probe one host, returning its config or None (never raises)."""
    url = f"ws://{ip}/{WS_PATH}"
    try:
        async with asyncio.timeout(timeout):
            async with session.ws_connect(url, protocols=[WS_SUBPROTOCOL]) as ws:
                await ws.send_bytes(build_frame(ZERO_SERIAL, "get", "config"))
                async for msg in ws:
                    if msg.type is aiohttp.WSMsgType.BINARY:
                        frame = parse_frame(msg.data)
                        if frame.command == "refresh" and frame.subcommand == "config":
                            return decode_config(frame.payload)
    except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ConnectionError):
        return None
    return None


async def async_scan(hass: HomeAssistant) -> dict[str, DeviceConfig]:
    """Scan the Home Assistant host's /24 for supported Reef Factory devices.

    Returns {ip: DeviceConfig} for every device whose serial starts with a
    supported family prefix (RFKH / RFDP).
    """
    try:
        local_ip = await network.async_get_source_ip(hass, target_ip="8.8.8.8")
    except (RuntimeError, OSError):
        return {}

    if not local_ip or local_ip.count(".") != 3:
        return {}

    base = local_ip.rsplit(".", 1)[0]
    session = async_get_clientsession(hass)
    semaphore = asyncio.Semaphore(SCAN_CONCURRENCY)
    found: dict[str, DeviceConfig] = {}

    async def _scan_one(host: str) -> None:
        async with semaphore:
            config = await _probe_quiet(session, host, SCAN_TIMEOUT)
        if config and config.serial.upper().startswith(SUPPORTED_FAMILIES):
            found[host] = config

    await asyncio.gather(*(_scan_one(f"{base}.{i}") for i in range(1, 255)))
    return found


class KhCoordinator(DataUpdateCoordinator[KhState | DpState]):
    """Owns the persistent WebSocket connection to one Reef Factory device.

    Handles multiple device families (KH Keeper, doser) over the same wire
    protocol; ``self.family`` selects the join sequence and frame decoders.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self.host: str = entry.data["host"]
        self.serial: str | None = entry.data.get(CONF_SERIAL)
        self.firmware: str = entry.data.get(CONF_FIRMWARE, "0.0.0")
        self.mac: str | None = entry.data.get(CONF_MAC)
        # Existing (pre-merge) KH entries have no stored family — detect it.
        self.family: str = (
            entry.data.get(CONF_FAMILY)
            or detect_family(self.serial or "")
            or FAMILY_KH
        )

        self._session = async_get_clientsession(hass)
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._task: asyncio.Task | None = None
        self._closing = False
        self._retry = 0
        self._last_logged: dict[tuple[str, str], bytes] = {}

        # Doser-only runtime state (not in the settings frame), carried across
        # settings refreshes and patched from status/dose frames.
        self._dp_dosing = False
        self._dp_last_dose_ml: float | None = None
        self._dp_last_dose_at = None
        self._dp_hist_task: asyncio.Task | None = None  # dose → refresh history
        self._dp_cooldown_until = 0.0  # loop-time writes wait until (post container write)
        # A manual dose/refill we initiated stays "cancelable" until the device
        # goes idle again — lets the card show CANCEL for immediate doses too,
        # without flipping on scheduled doses (which we did not start).
        self._dp_manual_active = False
        self._dp_manual_seen = False

    @property
    def model(self) -> str:
        """Human-readable device model for the family."""
        return MODELS.get(self.family, MODELS[FAMILY_KH])

    async def async_start(self) -> None:
        """Launch the background connection loop."""
        self._closing = False
        self._task = self.entry.async_create_background_task(
            self.hass, self._runner(), name=f"{DOMAIN}_{self.host}"
        )

    async def async_stop(self) -> None:
        """Stop the connection loop and close the socket."""
        self._closing = True
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._task and not self._task.done():
            self._task.cancel()

    # ------------------------------------------------------------------
    # Commands (device writes)
    # ------------------------------------------------------------------

    async def async_send(
        self, command: str, subcommand: str, payload: bytes = b"", identifier: str = ""
    ) -> None:
        """Send a command frame to the device over the LAN WebSocket."""
        ws = self._ws
        if ws is None or ws.closed or not self.serial:
            raise HomeAssistantError(f"{self.model} at {self.host} is not connected")

        _LOGGER.debug("TX %s/%s payload=%s", command, subcommand, payload.hex())
        await ws.send_bytes(
            build_frame(self.serial, command, subcommand, identifier, payload)
        )

    async def async_set_reagent(self, ml: float) -> None:
        """Set the remaining reagent level (mL). Benign — updates a tracked value."""
        await self.async_send("khSet", "reagent", encode_reagent(ml))

    async def async_measure_now(self) -> None:
        """Start a measurement now (runs a full titration cycle)."""
        await self.async_send("khMeasurement", "takeNow")

    async def async_cancel_measurement(self) -> None:
        """Cancel the measurement in progress."""
        await self.async_send("khMeasurement", "cancel")

    # -- Doser (RFDP) commands ------------------------------------------
    # Each carries an epoch-ms nonce (as the app does) and then asks for a
    # fresh settings frame so entities update immediately.

    def _dp_ident(self) -> str:
        return str(int(dt_util.utcnow().timestamp() * 1000))

    async def _dp_send(self, command: str, subcommand: str, payload: bytes = b"\x00") -> None:
        # Send the command only. We deliberately do NOT poke the device with an
        # immediate dpGet/settings afterwards: these are small ESP units with very
        # limited concurrent connections, and firing a second frame right after a
        # write (while the app/cloud may also be connected) can drop or crash them.
        # The device pushes a fresh settings frame on change, so HA still updates.
        # A recent container write may have bounced the device — wait out the
        # cooldown so this command doesn't land mid-reboot.
        wait = self._dp_cooldown_until - self.hass.loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        await self.async_send(command, subcommand, payload, self._dp_ident())

    async def async_dp_set_container(self, current_ml: float, capacity_ml: float) -> None:
        """Set reservoir level + capacity (e.g. after a refill)."""
        await self._dp_send("dpSet", "container", encode_dp_container(current_ml, capacity_ml))
        # Persisting a container change can reboot the device; hold other commands
        # off briefly so a follow-up (e.g. a manual dose) doesn't hit it mid-reboot.
        self._dp_cooldown_until = self.hass.loop.time() + DP_WRITE_COOLDOWN

    async def async_dp_manual_refill(self, amount_ml: float, days: int = 0) -> None:
        """Dose amount now (days=0) or spread over N days."""
        self._dp_manual_active = True
        self._dp_manual_seen = False
        await self._dp_send("dpManualRefill", "start", encode_dp_manual_refill(amount_ml, days))

    async def async_dp_stop_refill(self) -> None:
        """Cancel the active/pending manual refill/dose."""
        self._dp_manual_active = False
        self._dp_manual_seen = False
        self._dp_dosing = False
        # Revert the button/state right away — don't wait for a device frame, and
        # don't force a settings re-read (which could momentarily bounce values).
        if self.data is not None:
            self.async_set_updated_data(replace(self.data, dosing=False, manual_active=False))
        await self._dp_send("dpManualRefill", "stop", b"\x00")

    async def async_dp_skip_next(self, percent: int) -> None:
        """Skip a percentage (0-100) of the next scheduled dose."""
        await self._dp_send("dpSet", "skipNext", encode_dp_skip(percent))

    async def async_dp_write_doses(
        self, doses: list[tuple[int, float]], day_mask: int
    ) -> None:
        """Write the full dose schedule (times/volumes) + day mask."""
        await self._dp_send("dpSet", "doses", encode_dp_doses(doses, day_mask))

    async def async_dp_calibration_fill(self) -> None:
        """Calibration step: prime the tube (FILL THE CIRCUIT)."""
        await self._dp_send("dpCalibration", "circuitStart", b"\x00")

    async def async_dp_calibration_run(self) -> None:
        """Calibration step: run the pump ~30 s (dispense into a cup)."""
        await self._dp_send("dpCalibration", "start", b"\x00")

    async def async_dp_calibration_submit(
        self, measured_ml: float, period_code: int = 3
    ) -> None:
        """Submit the measured volume + set the recalibration reminder period."""
        ident = self._dp_ident()
        await self.async_send("dpCalibration", "value", encode_dp_calibration_value(measured_ml), ident)
        await self.async_send("dpCalibration", "notification", encode_dp_calibration_notification(period_code), ident)

    def _persist(self, key: str, value: str) -> None:
        """Persist a value into the config entry (survives restarts)."""
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, key: value}
        )

    async def _learn_mac(self) -> None:
        """Learn the device MAC once we're connected, for DHCP-based IP recovery.

        Run only after a confirmed connection (so `host` is the device's real
        current IP), then register it so Home Assistant's DHCP tracker can
        relocate the device by MAC. Best-effort — a missing MAC just falls back
        to the serial rescan.
        """
        if self.mac or get_mac_address is None:
            return
        try:
            raw = await self.hass.async_add_executor_job(
                lambda: get_mac_address(ip=self.host)
            )
        except Exception:  # noqa: BLE001 — best effort
            return
        if not raw:
            return

        self.mac = dr.format_mac(raw)
        self._persist(CONF_MAC, self.mac)
        _LOGGER.debug("KH Keeper %s MAC %s", self.serial, self.mac)

        # Entities registered before the MAC was known — add the connection now.
        registry = dr.async_get(self.hass)
        device = registry.async_get_device(
            identifiers={(DOMAIN, self.serial or self.host)}
        )
        if device:
            registry.async_update_device(
                device.id,
                merge_connections={(dr.CONNECTION_NETWORK_MAC, self.mac)},
            )

    async def _rediscover(self) -> None:
        """Find our device on the subnet by serial and adopt a new IP if it moved."""
        if not self.serial:
            return
        try:
            found = await async_scan(self.hass)
        except Exception:  # noqa: BLE001 — best effort
            return
        for ip, config in found.items():
            if config.serial == self.serial and ip != self.host:
                _LOGGER.info(
                    "KH Keeper %s moved: %s -> %s", self.serial, self.host, ip
                )
                self.host = ip
                self._persist(CONF_HOST, ip)
                return

    async def _runner(self) -> None:
        """Reconnect loop with progressive back-off and IP recovery."""
        while not self._closing:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError, ConnectionError) as err:
                self.async_set_update_error(UpdateFailed(str(err)))
                _LOGGER.debug("KH Keeper %s connection error: %s", self.host, err)
                # Device may have rebooted onto a new DHCP address — relocate it.
                await self._rediscover()
            except Exception as err:  # noqa: BLE001 — keep the loop alive
                self.async_set_update_error(UpdateFailed(str(err)))
                _LOGGER.exception("Unexpected KH Keeper error for %s", self.host)

            if self._closing:
                break

            delay = min(RECONNECT_MIN * (self._retry + 1), RECONNECT_MAX)
            self._retry += 1
            await asyncio.sleep(delay)

    async def _connect_and_listen(self) -> None:
        """One connection lifecycle: handshake, join, then listen with keepalive."""
        url = f"ws://{self.host}/{WS_PATH}"
        async with asyncio.timeout(CONNECT_TIMEOUT):
            ws = await self._session.ws_connect(url, protocols=[WS_SUBPROTOCOL])

        self._ws = ws
        self._retry = 0
        if not self.mac:
            self.hass.async_create_task(self._learn_mac())
        poll_task = (
            self.hass.async_create_task(self._dp_poll_loop(ws))
            if self.family == FAMILY_DP
            else None
        )
        try:
            await ws.send_bytes(build_frame(ZERO_SERIAL, "get", "config"))

            while not self._closing:
                try:
                    msg = await ws.receive(timeout=PING_INTERVAL)
                except asyncio.TimeoutError:
                    # Idle — ping and require a response, or the link is dead.
                    await ws.send_bytes(
                        build_frame(self.serial or ZERO_SERIAL, "ping", "ping")
                    )
                    try:
                        msg = await ws.receive(timeout=PONG_TIMEOUT)
                    except asyncio.TimeoutError as err:
                        # Half-open socket (e.g. device rebooted / changed IP).
                        raise ConnectionError("no response to ping") from err

                if msg.type is aiohttp.WSMsgType.BINARY:
                    await self._handle(ws, msg.data)
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    raise ConnectionError(f"socket closed ({msg.type.name})")
        finally:
            if poll_task is not None:
                poll_task.cancel()
            self._ws = None
            if not ws.closed:
                await ws.close()

    async def _dp_poll_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Pull a fresh doser settings frame every DP_POLL_INTERVAL so HA stays in
        sync with edits made in the RF app / on the device. One small read per
        cycle; stops as soon as this socket is replaced or closed."""
        try:
            while not self._closing and self._ws is ws and not ws.closed:
                await asyncio.sleep(DP_POLL_INTERVAL)
                if self.serial and self._ws is ws and not ws.closed:
                    await ws.send_bytes(build_frame(self.serial, "dpGet", "settings"))
        except (asyncio.CancelledError, ConnectionResetError, aiohttp.ClientError, RuntimeError):
            pass

    def _dp_refresh_after_dose(self) -> None:
        """A dose just fired — schedule one settings read so today's total/history
        update promptly. Triggered by an inbound device event (not our own write),
        so this read is safe. Debounced against bursts of dose frames."""
        if self._dp_hist_task and not self._dp_hist_task.done():
            self._dp_hist_task.cancel()
        self._dp_hist_task = self.hass.async_create_task(self._dp_settings_after(DP_DOSE_REFRESH_DELAY))

    async def _dp_settings_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            ws = self._ws
            if ws is not None and not ws.closed and self.serial:
                await ws.send_bytes(build_frame(self.serial, "dpGet", "settings"))
        except (asyncio.CancelledError, ConnectionResetError, aiohttp.ClientError, RuntimeError):
            pass

    def _sniff(self, frame) -> None:
        """Diagnostic: log every distinct frame at WARNING (readable in the HA log).

        De-duplicates by (command, subcommand) payload so a repeated identical
        settings push is not logged, but changes (a setting edit) and every
        measurement-in-progress frame (status/pH/calibration) are.
        """
        key = (frame.command, frame.subcommand)
        if self._last_logged.get(key) == frame.payload:
            return
        self._last_logged[key] = frame.payload
        _LOGGER.warning(
            "REEF-KH SNIFF %s/%s %dB: %s | %s",
            frame.command,
            frame.subcommand,
            len(frame.payload),
            frame.payload.hex(),
            _describe(frame),
        )

    async def _handle(self, ws: aiohttp.ClientWebSocketResponse, data: bytes) -> None:
        """Dispatch one incoming frame by device family."""
        frame = parse_frame(data)

        if self.entry.options.get(CONF_LOG_FRAMES):
            self._sniff(frame)

        if frame.command == "refresh" and frame.subcommand == "config":
            config = decode_config(frame.payload)
            self.serial = config.serial
            self.firmware = config.firmware
            _LOGGER.debug(
                "Reef Factory %s: serial=%s fw=%s family=%s",
                self.host, config.serial, config.firmware, self.family,
            )
            await self._join(ws, config.serial)
            return

        if self.family == FAMILY_DP:
            self._handle_dp(frame)
        else:
            self._handle_kh(frame)

    async def _join(self, ws: aiohttp.ClientWebSocketResponse, serial: str) -> None:
        """Send the family-specific join, then request full state."""
        pay = serial.encode("ascii") + b"\x00"
        if self.family == FAMILY_DP:
            # Connect topic varies by firmware — send both, then request state.
            await ws.send_bytes(build_frame(serial, "daConnect", "join", payload=pay))
            await ws.send_bytes(build_frame(serial, "dpConnect", "join", payload=pay))
            await ws.send_bytes(build_frame(serial, "dpGet", "all"))
        else:
            await ws.send_bytes(build_frame(serial, "khConnect", "join", payload=pay))

    def _handle_kh(self, frame) -> None:
        """KH Keeper frames: settings (full state) and status (live progress)."""
        if frame.command == "khRefresh" and frame.subcommand == "settings":
            try:
                state = decode_settings(frame.payload, tz=dt_util.DEFAULT_TIME_ZONE)
            except (ValueError, IndexError) as err:
                _LOGGER.warning("Bad settings frame from %s: %s", self.host, err)
                return
            self.async_set_updated_data(state)
        elif frame.command == "khRefresh" and frame.subcommand == "status":
            # Live measurement progress. Patch the current state if we have one.
            if self.data is not None:
                state_code, progress = decode_status(frame.payload)
                self.async_set_updated_data(
                    replace(
                        self.data,
                        measurement_state=state_code,
                        measurement_progress=progress,
                    )
                )
        # pH/server/alert/calibration frames carry no entity data yet; ignored.

    def _dp_track_manual(self, dosing: bool, refill_total_ml: float | None) -> bool:
        """Keep the 'manual dose/refill in progress' flag current and return the
        cancelable signal: True while an action we started is running, or while
        the device reports any pending refill (including one set from the app);
        clears once our action has run and the device is idle again."""
        running = dosing or bool(refill_total_ml)
        if self._dp_manual_active:
            if running:
                self._dp_manual_seen = True
            elif self._dp_manual_seen:
                self._dp_manual_active = False
                self._dp_manual_seen = False
        return self._dp_manual_active or bool(refill_total_ml)

    def _handle_dp(self, frame) -> None:
        """Doser frames: settings (level + schedule), status (live), dose."""
        if frame.command == "dpRefresh" and frame.subcommand == "settings":
            try:
                state = decode_dp_settings(frame.payload, tz=dt_util.DEFAULT_TIME_ZONE)
            except (ValueError, IndexError) as err:
                _LOGGER.debug("Bad dp settings frame from %s: %s", self.host, err)
                return
            self.async_set_updated_data(
                replace(
                    state,
                    dosing=self._dp_dosing,
                    last_dose_ml=self._dp_last_dose_ml,
                    last_dose_at=self._dp_last_dose_at,
                    manual_active=self._dp_track_manual(self._dp_dosing, state.refill_total_ml),
                )
            )
        elif frame.command == "dpRefresh" and frame.subcommand == "status":
            level, dosing = decode_dp_status(frame.payload)
            self._dp_dosing = dosing
            if self.data is not None:
                refill = self.data.refill_total_ml
                patch: dict = {
                    "dosing": dosing,
                    "manual_active": self._dp_track_manual(dosing, refill),
                }
                if level is not None:
                    patch["container_ml"] = level
                self.async_set_updated_data(replace(self.data, **patch))
        elif frame.command == "dpRefresh" and frame.subcommand == "dose":
            vol = decode_dp_dose(frame.payload)
            if vol is not None:
                self._dp_last_dose_ml = vol
                self._dp_last_dose_at = dt_util.utcnow()
                # A dose frame means that dose finished and the pump stopped. The
                # device does NOT reliably send a dosing=off status afterwards, so
                # 'dosing' would stick on and the manual CANCEL button never revert.
                # Clear both here — a one-shot manual dose is done. (A multi-day
                # refill keeps CANCEL via refill_total_ml.)
                self._dp_dosing = False
                self._dp_manual_active = False
                self._dp_manual_seen = False
                if self.data is not None:
                    self.async_set_updated_data(
                        replace(
                            self.data,
                            dosing=False,
                            last_dose_ml=vol,
                            last_dose_at=self._dp_last_dose_at,
                            manual_active=bool(self.data.refill_total_ml),
                        )
                    )
                # today's-total/history live in the settings frame — pull a fresh
                # one so they catch up in a couple seconds, not at the next poll.
                self._dp_refresh_after_dose()
