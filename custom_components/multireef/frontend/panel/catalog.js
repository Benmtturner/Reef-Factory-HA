// Multi Reef brand/model catalog — the one brand-aware surface.
//
// Devices are grouped by their HA DeviceInfo `manufacturer` → `model` (stable,
// machine-usable strings), NOT by scanning entity names. A model may carry a
// `card` descriptor (which Lovelace card to place + how to pick its entity +
// style variants); anchor keywords survive ONLY there, used to choose the
// card's `entity` from the device's own entities — never for discovery.
//
// `flowStep` maps a brand to its config-flow menu option so the add-device
// wizard can jump straight in per brand. `infrastructure: true` marks a hub
// (the EcoTech bridge, which HA reports as manufacturer "Multi Reef") so it's
// routed to the Bridges section, not the livestock-gear tree.

export const BRANDS = [
  {
    id: "reef_factory",
    label: "Reef Factory",
    manufacturer: "Reef Factory",
    icon: "mdi:flask-outline",
    flowStep: "reef_factory",
    models: {
      "KH Keeper": { icon: "mdi:test-tube" },
      Doser: {
        icon: "mdi:water-pump",
        card: {
          type: "custom:reef-factory-doser-card",
          anchor: { domain: "sensor", keyword: "container_level" },
          options: { grid_options: { columns: "full" } },
        },
      },
    },
  },
  {
    id: "redsea",
    label: "Red Sea",
    manufacturer: "Red Sea",
    icon: "mdi:water-plus",
    flowStep: "redsea",
    // Prefix match: "ReefDose 2" and "ReefDose 4" share one card.
    modelPrefix: {
      ReefDose: {
        icon: "mdi:water-plus",
        card: {
          type: "custom:reef-dose-card",
          anchor: { domain: "sensor", keyword: "head_1_dosed_today" },
          options: { grid_options: { columns: "full" } },
          variants: [
            {
              key: "settings",
              label: "Head details",
              options: [
                ["drawer", "Collapsed — tap a head to open"],
                ["inline", "Always expanded"],
              ],
            },
          ],
        },
      },
    },
  },
  {
    id: "ecotech",
    label: "EcoTech Marine",
    manufacturer: "EcoTech Marine",
    icon: "mdi:waves",
    flowStep: "bridge",
    models: {
      "VorTech MP10": { icon: "mdi:fan" },
    },
  },
  {
    // The ESP32 Mobius bridge hub — HA DeviceInfo manufacturer is "Multi Reef".
    // Infrastructure, not gear: routed to the Bridges section, hidden from the tree.
    id: "multireef_infra",
    label: "Multi Reef",
    manufacturer: "Multi Reef",
    icon: "mdi:access-point",
    flowStep: "bridge",
    infrastructure: true,
  },
];

const BY_MANUFACTURER = new Map(BRANDS.map((b) => [b.manufacturer, b]));

/** Brand entry for a DeviceInfo manufacturer, or undefined (→ "Other" bucket). */
export function brandFor(manufacturer) {
  return BY_MANUFACTURER.get(manufacturer);
}

/** True if this manufacturer is a hub (bridge), not a listable device. */
export function isInfrastructure(manufacturer) {
  return !!BY_MANUFACTURER.get(manufacturer)?.infrastructure;
}

/** Model metadata {icon, card?} for a manufacturer+model — exact then prefix. */
export function modelMeta(manufacturer, model) {
  const brand = BY_MANUFACTURER.get(manufacturer);
  if (!brand || !model) return undefined;
  if (brand.models && brand.models[model]) return brand.models[model];
  if (brand.modelPrefix) {
    for (const [prefix, meta] of Object.entries(brand.modelPrefix)) {
      if (model.startsWith(prefix)) return meta;
    }
  }
  return undefined;
}

/** The card descriptor for a manufacturer+model, or undefined. */
export function cardFor(manufacturer, model) {
  return modelMeta(manufacturer, model)?.card;
}

/** Brands that can be added via the wizard (exclude pure infrastructure). */
export function addableBrands() {
  return BRANDS.filter((b) => !b.infrastructure);
}
