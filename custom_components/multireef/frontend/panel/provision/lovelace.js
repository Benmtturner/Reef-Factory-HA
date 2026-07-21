// Pure Lovelace helpers for card provisioning — no DOM, unit-testable.
// Behavior is a byte-identical port of the original panel's dialog logic.

/** Storage-mode dashboards, with the default Overview prepended when absent. */
export async function loadDashboards(hass) {
  let list = [];
  try {
    list = await hass.callWS({ type: "lovelace/dashboards/list" });
  } catch (e) {
    list = [];
  }
  const dashes = (list || [])
    .filter((d) => d.mode === "storage")
    .map((d) => ({ url_path: d.url_path, title: d.title || d.url_path }));
  if (!dashes.some((d) => d.url_path === "lovelace")) {
    dashes.unshift({ url_path: null, title: "Overview (default)" });
  }
  return dashes;
}

/** Full config of one dashboard (caller keeps it for the save round-trip). */
export function loadViews(hass, urlPath) {
  return hass.callWS({ type: "lovelace/config", url_path: urlPath });
}

/** Persist an edited dashboard config. */
export function saveConfig(hass, urlPath, config) {
  return hass.callWS({ type: "lovelace/config/save", url_path: urlPath, config });
}

/** Build the card config from catalog metadata + chosen variant values. */
export function buildCard(cardMeta, anchorEntity, variantValues = {}) {
  const card = { type: cardMeta.type, entity: anchorEntity, ...(cardMeta.options || {}) };
  for (const v of cardMeta.variants || []) {
    const val = variantValues[v.key];
    if (val) card[v.key] = val;
  }
  return card;
}

/** Append into sections[0].cards (creating a grid section) or view.cards. */
export function appendCard(view, card) {
  if (Array.isArray(view.sections)) {
    if (!view.sections.length) view.sections.push({ type: "grid", cards: [] });
    const sec = view.sections[0];
    sec.cards = sec.cards || [];
    sec.cards.push(card);
    return true;
  }
  if (Array.isArray(view.cards)) {
    view.cards.push(card);
    return true;
  }
  return false;
}

/** Recursive duplicate check on (type, entity) across sections/nested cards. */
export function alreadyHas(view, cardType, anchorEntity) {
  const match = (c) => c && c.type === cardType && c.entity === anchorEntity;
  const scan = (cards) =>
    Array.isArray(cards) &&
    cards.some((c) => match(c) || scan(c?.cards) || (c?.sections || []).some((s) => scan(s.cards)));
  if (Array.isArray(view.sections)) return view.sections.some((s) => scan(s.cards));
  return scan(view.cards);
}
