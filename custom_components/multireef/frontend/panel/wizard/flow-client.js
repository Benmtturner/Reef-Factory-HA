// Pure config-flow REST client + schema normalizer — no DOM, unit-testable.
//
// Drives our own config flow via HA's public REST API so the panel's add-device
// wizard needs no HA internals. The wizard renders on step.type only; this
// module turns HA's serialized voluptuous schema into a small field list the
// wizard can render generically (and never hard-fails on an unknown shape).

const DOMAIN = "multireef";

export function createFlow(hass) {
  return hass.callApi("post", "config/config_entries/flow", {
    handler: DOMAIN,
    show_advanced_options: false,
  });
}

export function submitStep(hass, flowId, userInput) {
  return hass.callApi("post", `config/config_entries/flow/${flowId}`, userInput);
}

export function abortFlow(hass, flowId) {
  return hass.callApi("delete", `config/config_entries/flow/${flowId}`);
}

/** Normalize serialized options to [[value, label], …]. */
function normOptions(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) {
    return raw.map((o) => {
      if (Array.isArray(o)) return [String(o[0]), String(o[1] ?? o[0])];
      if (o && typeof o === "object") return [String(o.value), String(o.label ?? o.value)];
      return [String(o), String(o)];
    });
  }
  if (typeof raw === "object") return Object.entries(raw).map(([k, v]) => [String(k), String(v)]);
  return [];
}

/**
 * Serialized voluptuous / selector schema → Field[].
 * Field = { name, required, default, kind:"text"|"select"|"boolean"|"number",
 *           options?, unknown? }
 */
export function normalizeSchema(dataSchema) {
  if (!Array.isArray(dataSchema)) return [];
  return dataSchema.map((f) => {
    // vol.Required serializes to required:true; vol.Optional to optional:true.
    const base = { name: f.name, required: f.required === true, default: f.default };
    // Selector-based (newer flows). Ours uses raw types, but stay robust.
    const sel = f.selector;
    if (sel && typeof sel === "object") {
      if (sel.select) return { ...base, kind: "select", options: normOptions(sel.select.options) };
      if (sel.boolean !== undefined) return { ...base, kind: "boolean" };
      if (sel.number) return { ...base, kind: "number" };
      if (sel.text !== undefined) return { ...base, kind: "text" };
      return { ...base, kind: "text", unknown: true };
    }
    // Raw voluptuous types.
    if (f.type === "select" || f.options) {
      return { ...base, kind: "select", options: normOptions(f.options) };
    }
    if (f.type === "boolean") return { ...base, kind: "boolean" };
    if (f.type === "integer" || f.type === "float" || f.type === "number") {
      return { ...base, kind: "number" };
    }
    if (f.type === "string") return { ...base, kind: "text" };
    return { ...base, kind: "text", unknown: true };
  });
}
