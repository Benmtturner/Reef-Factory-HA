// Multi Reef panel — tiny shared utilities (no dependencies).

/** HTML-escape every interpolated string — device/area names are user input. */
export function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

/** Trailing-edge debounce. */
export function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** Fire a composed, bubbling custom event. */
export function fireEvent(target, type, detail) {
  target.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

/** SPA-navigate inside Home Assistant (its router listens for location-changed). */
export function navigate(path, { replace = false } = {}) {
  if (replace) {
    window.history.replaceState(null, "", path);
  } else {
    window.history.pushState(null, "", path);
  }
  fireEvent(window, "location-changed", { replace });
}

/** localStorage JSON helpers (never throw — storage may be unavailable). */
export function loadJSON(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}
export function saveJSON(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    /* storage full/blocked — non-fatal */
  }
}
