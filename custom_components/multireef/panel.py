"""Multi Reef sidebar panel — the integration's front door.

The panel is a full-page custom element (an ES-module app under
``frontend/panel/``) served by this integration and registered in the HA
sidebar. All panel logic runs client-side against the authenticated ``hass``
object (WebSocket registries, Lovelace API, config-flow REST), so there is
nothing to do here beyond serving the directory + registering the entry module.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "multi-reef"
# The whole panel directory is served so the entry's relative ES imports work.
PANEL_ASSETS_URL = f"/{DOMAIN}/panel"
_PANEL_DIR = "frontend/panel"
_ENTRY = "multi-reef-panel.js"
_WEBCOMPONENT = "multi-reef-panel"


async def async_register_multi_reef_panel(hass: HomeAssistant) -> None:
    """Serve and register the Multi Reef sidebar panel (once per HA run)."""
    key = f"{DOMAIN}_panel_registered"
    if hass.data.get(key):
        return
    hass.data[key] = True
    panel_dir = Path(__file__).parent / _PANEL_DIR

    # Cache-bust the entry on the integration version so a HACS update reloads
    # the panel without a manual hard-refresh (same pattern as the cards).
    # Submodules are served with cache_headers=False and revalidate on mtime.
    try:
        integration = await async_get_integration(hass, DOMAIN)
        version = str(integration.version) if integration.version else "0"
    except Exception:  # noqa: BLE001
        version = "0"

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_ASSETS_URL, str(panel_dir), False)]
        )
        kwargs = {
            "frontend_url_path": PANEL_URL_PATH,
            "webcomponent_name": _WEBCOMPONENT,
            "module_url": f"{PANEL_ASSETS_URL}/{_ENTRY}?v={version}",
            "sidebar_title": "Multi Reef",
            "sidebar_icon": "mdi:fishbowl",
            "require_admin": True,
            "embed_iframe": False,
            "trust_external": False,
        }
        try:
            # The panel receives this as `panel.config` (About footer/banner).
            await async_register_panel(hass, config={"version": version}, **kwargs)
        except TypeError:
            # Older HA without the config kwarg — register without it.
            await async_register_panel(hass, **kwargs)
        _LOGGER.debug("Multi Reef panel registered at /%s (v%s)", PANEL_URL_PATH, version)
    except Exception:  # noqa: BLE001 — a panel failure must never break the device
        _LOGGER.warning("Could not register the Multi Reef panel", exc_info=True)
