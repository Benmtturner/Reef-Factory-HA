"""The Reef Factory integration (KH Keeper + single-head doser)."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.loader import async_get_integration
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ECOTECH_PLATFORMS,
    ENTRY_TYPE_ECOTECH_BRIDGE,
    ENTRY_TYPE_REDSEA_ATO,
    ENTRY_TYPE_REDSEA_DOSER,
    FAMILY_DP,
    PLATFORMS,
    REDSEA_ATO_PLATFORMS,
    REDSEA_PLATFORMS,
)
from .coordinator import KhCoordinator
from .ecotech.coordinator import EcoTechCoordinator
from .ecotech.entity import bridge_device_info
from .panel import async_register_multi_reef_panel
from .redsea.ato import RedSeaAtoCoordinator
from .redsea.coordinator import RedSeaDoserCoordinator

_LOGGER = logging.getLogger(__name__)

type KhConfigEntry = ConfigEntry[KhCoordinator]

# Fallback only — the ?v= cache-buster tracks the integration (manifest) version
# so every release reloads the card in the browser automatically.
CARD_VERSION = "0.18.0"


async def _serve_card(hass: HomeAssistant, filename: str) -> None:
    """Serve a bundled Lovelace card and auto-load it into the frontend (once).

    Cache-busts on the integration version so a HACS update reloads it in the
    browser without a manual hard-refresh.
    """
    key = f"{DOMAIN}_card_{filename}"
    if hass.data.get(key):
        return
    hass.data[key] = True
    url = f"/{DOMAIN}/{filename}"
    card_path = Path(__file__).parent / "frontend" / filename
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version) if integration.version else CARD_VERSION
    except Exception:  # noqa: BLE001
        version = CARD_VERSION
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(url, str(card_path), False)]
        )
        add_extra_js_url(hass, f"{url}?v={version}")
        # extra_js loads fire-and-forget, so a cold (hard-refresh) page can
        # render the dashboard before the module arrives. Lovelace *resources*
        # are awaited before first render, so register one of those too; the
        # cards' define-guards make the double load a no-op.
        await _ensure_lovelace_resource(hass, f"{url}?v={version}")
        _LOGGER.debug("Multi Reef card registered at %s", url)
    except Exception:  # noqa: BLE001 — a card failure must never break the device
        _LOGGER.warning("Could not register card %s", filename, exc_info=True)


async def _ensure_lovelace_resource(hass: HomeAssistant, versioned_url: str) -> None:
    """Create or update the storage-mode Lovelace resource for a card URL.

    YAML-mode Lovelace has no resource storage; in that case (or on any
    surprise) we leave the extra_js registration to do its best.
    """
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None:
            return
        if not resources.loaded:
            await resources.async_load()
        base = versioned_url.split("?")[0]
        for item in resources.async_items():
            if (item.get("url") or "").split("?")[0] == base:
                if item.get("url") != versioned_url:
                    await resources.async_update_item(
                        item["id"], {"url": versioned_url}
                    )
                return
        await resources.async_create_item(
            {"res_type": "module", "url": versioned_url}
        )
    except Exception:  # noqa: BLE001 — never let resource bookkeeping break setup
        _LOGGER.debug(
            "Could not register Lovelace resource %s", versioned_url, exc_info=True
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Multi Reef entry — a Reef Factory device or an EcoTech bridge."""
    # The Multi Reef console is available whenever the integration is set up.
    await async_register_multi_reef_panel(hass)

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_ECOTECH_BRIDGE:
        coordinator = EcoTechCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        # Register the bridge hub device up front so child devices' via_device
        # links resolve — platforms set up concurrently, so ordering can't ensure it.
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, **bridge_device_info(coordinator)
        )
        await hass.config_entries.async_forward_entry_setups(entry, ECOTECH_PLATFORMS)
        return True

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_REDSEA_DOSER:
        coordinator = RedSeaDoserCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await _serve_card(hass, "reef-dose-card.js")
        await hass.config_entries.async_forward_entry_setups(entry, REDSEA_PLATFORMS)
        return True

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_REDSEA_ATO:
        coordinator = RedSeaAtoCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await _serve_card(hass, "tank-temp-controller-card.js")
        await hass.config_entries.async_forward_entry_setups(
            entry, REDSEA_ATO_PLATFORMS
        )
        return True

    # Reef Factory device (the original path).
    coordinator = KhCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator
    if coordinator.family == FAMILY_DP:
        await _serve_card(hass, "reef-factory-doser-card.js")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = entry.runtime_data
    if isinstance(coordinator, EcoTechCoordinator):
        platforms = ECOTECH_PLATFORMS
    elif isinstance(coordinator, RedSeaDoserCoordinator):
        platforms = REDSEA_PLATFORMS
    elif isinstance(coordinator, RedSeaAtoCoordinator):
        platforms = REDSEA_ATO_PLATFORMS
    else:
        platforms = PLATFORMS
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unload_ok and isinstance(coordinator, KhCoordinator):
        await coordinator.async_stop()
    return unload_ok
