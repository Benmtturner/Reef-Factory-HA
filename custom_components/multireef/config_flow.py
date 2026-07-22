"""Config flow for the Reef Factory KH Keeper.

By default it scans the local network and lets you pick the discovered device —
no IP typing. Manual IP entry remains as a fallback (e.g. the device is on a
different subnet/VLAN than Home Assistant).
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .const import (
    CONF_BRIDGE_HOST,
    CONF_ENTRY_TYPE,
    CONF_FAMILY,
    CONF_FIRMWARE,
    CONF_LOG_FRAMES,
    CONF_MAC,
    CONF_REDSEA_HWID,
    CONF_REDSEA_MODEL,
    CONF_SERIAL,
    ENTRY_TYPE_ECOTECH_BRIDGE,
    ENTRY_TYPE_REDSEA_ATO,
    ENTRY_TYPE_REDSEA_DOSER,
    MODELS,
    DOMAIN,
)
from .coordinator import async_probe, async_scan
from .ecotech.bridge import MobiusBridge
from .ecotech.const import DEFAULT_BRIDGE_HOST
from .protocol import DeviceConfig, detect_family
from .redsea.const import DOSER_MODELS, SUPPORTED_MODELS
from .redsea.coordinator import async_probe_doser, async_scan_dosers


def _model_for(serial: str) -> str:
    """Model name for a serial's family, falling back to a generic label."""
    family = detect_family(serial)
    return MODELS.get(family, "Device") if family else "Device"

_LOGGER = logging.getLogger(__name__)


async def _probe_bridge(hass: HomeAssistant, host: str) -> dict:
    """Validate a Multi Reef bridge is reachable by reading /health."""
    bridge = MobiusBridge(async_get_clientsession(hass), host)
    return await bridge.health()


MANUAL = "__manual__"

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_NAME): str,
    }
)


class KhConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a KH Keeper."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, DeviceConfig] = {}
        self._redsea: dict[str, dict] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return KhOptionsFlow()

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """A registered device got a DHCP lease — relocate ours if its IP changed."""
        mac = format_mac(discovery_info.macaddress)
        for entry in self._async_current_entries():
            if entry.data.get(CONF_MAC) == mac:
                return self.async_update_reload_and_abort(
                    entry,
                    data={**entry.data, CONF_HOST: discovery_info.ip},
                    reason="already_configured",
                )
        return self.async_abort(reason="not_ours")

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick what to add: a Reef Factory device, an EcoTech bridge, or Red Sea."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["reef_factory", "bridge", "redsea"],
        )

    async def async_step_reef_factory(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scan the network, then pick a device or fall back to manual entry."""
        found = await async_scan(self.hass)

        # Drop devices that are already configured.
        configured = self._async_current_ids()
        self._discovered = {
            ip: cfg for ip, cfg in found.items() if cfg.serial not in configured
        }

        if self._discovered:
            return await self.async_step_pick()
        return await self.async_step_manual()

    async def async_step_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add an EcoTech bridge by address (defaults to multireef.local)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_BRIDGE_HOST].strip()
            try:
                await _probe_bridge(self.hass, host)
            except Exception:  # noqa: BLE001 — surfaced as a form error
                _LOGGER.exception("Failed to reach bridge %s", host)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"bridge_{host}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Multi Reef Bridge",
                    data={
                        CONF_ENTRY_TYPE: ENTRY_TYPE_ECOTECH_BRIDGE,
                        CONF_BRIDGE_HOST: host,
                    },
                )
        return self.async_show_form(
            step_id="bridge",
            data_schema=vol.Schema(
                {vol.Required(CONF_BRIDGE_HOST, default=DEFAULT_BRIDGE_HOST): str}
            ),
            errors=errors,
        )

    # -- Red Sea (ReefBeat) ---------------------------------------------------

    async def async_step_redsea(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scan the network for ReefBeat devices, then pick or enter manually."""
        found = await async_scan_dosers(self.hass)
        configured = self._async_current_ids()
        self._redsea = {
            ip: info
            for ip, info in found.items()
            if (info.get("hwid") or ip) not in configured
        }
        if self._redsea:
            return await self.async_step_redsea_pick()
        return await self.async_step_redsea_manual()

    async def async_step_redsea_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one of the discovered ReefBeat devices."""
        if user_input is not None:
            choice = user_input[CONF_HOST]
            if choice == MANUAL:
                return await self.async_step_redsea_manual()
            info = self._redsea[choice]
            await self.async_set_unique_id(info.get("hwid") or choice)
            self._abort_if_unique_id_configured()
            return self._create_redsea_entry(choice, info)

        options = {
            ip: f"{SUPPORTED_MODELS.get(info.get('hw_model', ''), 'ReefBeat device')} — {ip}"
            for ip, info in self._redsea.items()
        }
        options[MANUAL] = "Enter IP address manually…"
        return self.async_show_form(
            step_id="redsea_pick",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(options)}),
        )

    async def async_step_redsea_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual IP entry for a ReefBeat device (reliable fallback)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                info = await async_probe_doser(self.hass, host)
            except Exception:  # noqa: BLE001 — surfaced as a form error
                _LOGGER.exception("Failed to probe ReefDose %s", host)
                errors["base"] = "cannot_connect"
            else:
                if str(info.get("hw_model") or "") not in SUPPORTED_MODELS:
                    errors["base"] = "not_supported"
                else:
                    await self.async_set_unique_id(info.get("hwid") or host)
                    self._abort_if_unique_id_configured()
                    return self._create_redsea_entry(host, info)
        return self.async_show_form(
            step_id="redsea_manual", data_schema=MANUAL_SCHEMA, errors=errors
        )

    def _create_redsea_entry(self, host: str, info: dict) -> ConfigFlowResult:
        """Create the config entry for a confirmed ReefBeat device."""
        model = str(info.get("hw_model") or "RSDOSE2")
        title = info.get("name") or SUPPORTED_MODELS.get(model, "ReefBeat device")
        entry_type = (
            ENTRY_TYPE_REDSEA_DOSER if model in DOSER_MODELS else ENTRY_TYPE_REDSEA_ATO
        )
        return self.async_create_entry(
            title=title,
            data={
                CONF_ENTRY_TYPE: entry_type,
                CONF_HOST: host,
                CONF_REDSEA_HWID: info.get("hwid", ""),
                CONF_REDSEA_MODEL: model,
            },
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose one of the discovered KH Keepers."""
        if user_input is not None:
            choice = user_input[CONF_HOST]
            if choice == MANUAL:
                return await self.async_step_manual()

            config = self._discovered[choice]
            await self.async_set_unique_id(config.serial)
            self._abort_if_unique_id_configured()
            return self._create_entry(choice, config)

        options = {
            ip: f"{_model_for(cfg.serial)} {cfg.serial[-4:]} — {ip}"
            for ip, cfg in self._discovered.items()
        }
        options[MANUAL] = "Enter IP address manually…"

        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(options)}),
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual IP entry fallback."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                config = await async_probe(self.hass, host)
            except Exception:  # noqa: BLE001 — surfaced as a form error
                _LOGGER.exception("Failed to probe %s", host)
                errors["base"] = "cannot_connect"
            else:
                if detect_family(config.serial) is None:
                    errors["base"] = "not_supported"
                else:
                    await self.async_set_unique_id(config.serial)
                    self._abort_if_unique_id_configured()
                    return self._create_entry(
                        host, config, name=user_input.get(CONF_NAME)
                    )

        return self.async_show_form(
            step_id="manual", data_schema=MANUAL_SCHEMA, errors=errors
        )

    def _create_entry(
        self, host: str, config: DeviceConfig, name: str | None = None
    ) -> ConfigFlowResult:
        """Create the config entry for a confirmed device."""
        title = name or f"{_model_for(config.serial)} {config.serial[-4:]}"
        return self.async_create_entry(
            title=title,
            data={
                CONF_HOST: host,
                CONF_NAME: title,
                CONF_SERIAL: config.serial,
                CONF_FIRMWARE: config.firmware,
                CONF_FAMILY: detect_family(config.serial),
            },
        )


class KhOptionsFlow(OptionsFlow):
    """Options: diagnostic frame logging toggle."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(CONF_LOG_FRAMES, False)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Optional(CONF_LOG_FRAMES, default=current): bool}
            ),
        )
