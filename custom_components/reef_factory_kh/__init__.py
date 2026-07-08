"""The Reef Factory KH Keeper integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import KhCoordinator

type KhConfigEntry = ConfigEntry[KhCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: KhConfigEntry) -> bool:
    """Set up a KH Keeper from a config entry."""
    coordinator = KhCoordinator(hass, entry)
    await coordinator.async_start()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KhConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok
