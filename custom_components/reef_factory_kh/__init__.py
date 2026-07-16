"""The Reef Factory integration (KH Keeper + single-head doser)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, FAMILY_DP, PLATFORMS
from .coordinator import KhCoordinator
from .panel import async_register_multi_reef_panel

_LOGGER = logging.getLogger(__name__)

type KhConfigEntry = ConfigEntry[KhCoordinator]

CARD_URL = f"/{DOMAIN}/reef-factory-doser-card.js"
_CARD_FILE = "frontend/reef-factory-doser-card.js"
# Bump when the card JS changes so the browser reloads it (?v= cache-buster).
CARD_VERSION = "0.10.3"


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled doser card and auto-load it into the frontend (once)."""
    key = f"{DOMAIN}_card_registered"
    if hass.data.get(key):
        return
    hass.data[key] = True
    card_path = Path(__file__).parent / _CARD_FILE
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_path), False)]
        )
        add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
        _LOGGER.debug("Reef Factory doser card registered at %s", CARD_URL)
    except Exception:  # noqa: BLE001 — a card failure must never break the device
        _LOGGER.warning("Could not register the Reef Factory doser card", exc_info=True)


async def async_setup_entry(hass: HomeAssistant, entry: KhConfigEntry) -> bool:
    """Set up a Reef Factory device from a config entry."""
    coordinator = KhCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator

    # The Multi Reef console is available whenever the integration is set up.
    await async_register_multi_reef_panel(hass)

    if coordinator.family == FAMILY_DP:
        await _async_register_card(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KhConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok
