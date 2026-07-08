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
from homeassistant.core import callback

from .const import (
    CONF_FIRMWARE,
    CONF_LOG_FRAMES,
    CONF_SERIAL,
    DEVICE_FAMILY,
    DOMAIN,
    MODEL,
)
from .coordinator import async_probe, async_scan
from .protocol import DeviceConfig

_LOGGER = logging.getLogger(__name__)

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return KhOptionsFlow()

    async def async_step_user(
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
            ip: f"{MODEL} {cfg.serial[-4:]} — {ip}"
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
                if not config.serial.upper().startswith(DEVICE_FAMILY):
                    errors["base"] = "not_kh"
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
        title = name or f"{MODEL} {config.serial[-4:]}"
        return self.async_create_entry(
            title=title,
            data={
                CONF_HOST: host,
                CONF_NAME: title,
                CONF_SERIAL: config.serial,
                CONF_FIRMWARE: config.firmware,
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
