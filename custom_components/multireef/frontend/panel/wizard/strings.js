// Fallback wizard copy — mirrors strings.json config.step.*. The wizard tries
// hass localize first (so translated/edited flow copy wins); this is the safety
// net when localize is unavailable in the panel context.

export const MENU = {
  reef_factory: "Reef Factory device (KH Keeper, doser)",
  bridge: "EcoTech bridge (VorTech, Radion…)",
  redsea: "Red Sea (ReefDose…)",
};

// Rich presentation for the menu (icon + one-liner), keyed by menu option id.
export const MENU_PRESENTATION = {
  reef_factory: { icon: "mdi:flask-outline", blurb: "KH Keeper, single-head doser" },
  bridge: { icon: "mdi:access-point", blurb: "VorTech / Radion via a Multi Reef bridge" },
  redsea: { icon: "mdi:water-plus", blurb: "ReefDose dosers on your network" },
};

export const STEPS = {
  bridge: {
    title: "Add EcoTech bridge",
    description: "Enter the Multi Reef bridge's address. Leave the default if you flashed it as multireef.local.",
    data: { bridge_host: "Bridge address (host or IP)" },
  },
  pick: {
    title: "Select your device",
    description: "These Reef Factory devices were found on your network. Pick one, or choose manual entry.",
    data: { host: "Device" },
  },
  manual: {
    title: "Enter device IP",
    description: "No device was found automatically, or you chose manual entry. Enter the LAN IP address.",
    data: { host: "IP address", name: "Name (optional)" },
  },
  redsea_pick: {
    title: "Select your ReefDose",
    description: "These Red Sea ReefDose dosers were found on your network. Pick one, or choose manual entry.",
    data: { host: "Device" },
  },
  redsea_manual: {
    title: "Enter ReefDose IP",
    description: "No ReefDose was found automatically, or you chose manual entry. Enter its LAN IP address.",
    data: { host: "IP address", name: "Name (optional)" },
  },
};

export const ERRORS = {
  cannot_connect: "Could not reach the device. Check the IP and that it's on the same network.",
  not_supported: "That device responded but isn't supported for this option.",
};

export const ABORTS = {
  already_configured: "This device is already set up.",
  not_ours: "That device isn't a Multi Reef device.",
};

// Steps whose submission runs a network scan on the backend (show a spinner).
export const SCAN_STEPS = new Set(["reef_factory", "redsea"]);

/** Humanize a raw key for a last-resort label. */
export function humanize(key) {
  return String(key || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
