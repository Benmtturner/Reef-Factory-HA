"""Multi Reef sidebar panel — the config engine (device → dashboard provisioning).

The panel is a full-page custom element served by this integration and registered
in the HA sidebar. All provisioning logic (list dashboards, splice a card into a
view, save) runs client-side in the panel via ``hass.callWS`` against the Lovelace
WebSocket API, so there is nothing to do here beyond serving + registering it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "multi-reef"
PANEL_JS_URL = f"/{DOMAIN}/multi-reef-panel.js"
_PANEL_FILE = "frontend/multi-reef-panel.js"
_WEBCOMPONENT = "multi-reef-panel"
# Bump when the panel JS changes so the browser reloads it (?v= cache-buster).
PANEL_VERSION = "0.5.2"


async def async_register_multi_reef_panel(hass: HomeAssistant) -> None:
    """Serve and register the Multi Reef sidebar panel (once per HA run)."""
    key = f"{DOMAIN}_panel_registered"
    if hass.data.get(key):
        return
    hass.data[key] = True
    js_path = Path(__file__).parent / _PANEL_FILE
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_JS_URL, str(js_path), False)]
        )
        await async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=_WEBCOMPONENT,
            module_url=f"{PANEL_JS_URL}?v={PANEL_VERSION}",
            sidebar_title="Multi Reef",
            sidebar_icon="mdi:fishbowl",
            require_admin=True,
            embed_iframe=False,
            trust_external=False,
        )
        _LOGGER.debug("Multi Reef panel registered at /%s", PANEL_URL_PATH)
    except Exception:  # noqa: BLE001 — a panel failure must never break the device
        _LOGGER.warning("Could not register the Multi Reef panel", exc_info=True)
