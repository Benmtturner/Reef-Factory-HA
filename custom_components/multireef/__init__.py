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


# All cards ship as ONE module. Separately-registered modules proved
# unreliable on cold loads: Chrome can fetch a later extra module (200) and
# still never evaluate it after a hard refresh, while the first-position
# module evaluates every time. One file, one evaluation, every card defined
# (each card is define-guarded, so absent devices cost nothing).
_CARD_FILES = (
    "reef-dose-card.js",
    "reef-factory-doser-card.js",
    "tank-temp-controller-card.js",
)
_CARDS_BUNDLE = "multireef-cards.js"


async def _serve_cards(hass: HomeAssistant) -> None:
    """Bundle and serve every Lovelace card, auto-loaded into the frontend (once).

    Cache-busts on the integration version so a HACS update reloads the cards
    in the browser without a manual hard-refresh.
    """
    key = f"{DOMAIN}_cards_bundle"
    if hass.data.get(key):
        return
    hass.data[key] = True
    frontend_dir = Path(__file__).parent / "frontend"
    bundle_path = frontend_dir / _CARDS_BUNDLE

    def _build_bundle() -> None:
        parts = [
            (frontend_dir / name).read_text(encoding="utf-8")
            for name in _CARD_FILES
        ]
        bundle_path.write_text("\n;\n".join(parts), encoding="utf-8")

    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version) if integration.version else CARD_VERSION
    except Exception:  # noqa: BLE001
        version = CARD_VERSION
    try:
        await hass.async_add_executor_job(_build_bundle)
        url = f"/{DOMAIN}/{_CARDS_BUNDLE}"
        # Keep the individual files reachable too (debugging, direct links).
        paths = [StaticPathConfig(url, str(bundle_path), False)]
        paths += [
            StaticPathConfig(
                f"/{DOMAIN}/{name}", str(frontend_dir / name), False
            )
            for name in _CARD_FILES
        ]
        await hass.http.async_register_static_paths(paths)
        add_extra_js_url(hass, f"{url}?v={version}")
        await _ensure_lovelace_resource(hass, f"{url}?v={version}")
        _LOGGER.debug("Multi Reef cards bundle registered at %s", url)
    except Exception:  # noqa: BLE001 — a card failure must never break the device
        _LOGGER.warning("Could not register cards bundle", exc_info=True)


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
        # Prune resources from the pre-bundle era so cards load exactly once.
        for item in list(resources.async_items()):
            item_url = item.get("url") or ""
            if item_url.startswith(f"/{DOMAIN}/") and item_url.split("?")[0] != base:
                await resources.async_delete_item(item["id"])
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
    await _serve_cards(hass)

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
        await hass.config_entries.async_forward_entry_setups(entry, REDSEA_PLATFORMS)
        return True

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_REDSEA_ATO:
        coordinator = RedSeaAtoCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(
            entry, REDSEA_ATO_PLATFORMS
        )
        return True

    # Reef Factory device (the original path).
    coordinator = KhCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator
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
