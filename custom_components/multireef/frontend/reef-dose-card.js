// Multi Reef — Red Sea ReefDose card.
//
// A light-themed dosing card modelled on the ReefBeat app: a device header with a
// heads on/off toggle, then one row per head (supplement, dosed/daily with a
// progress bar, doses + days-left chips, a status bottle, Dose Now, and a schedule
// toggle) plus an expandable settings drawer.
//
// Config:  type: custom:reef-dose-card
//          entity: <any entity of the ReefDose device>   (used to find its siblings)
//
// It resolves every sibling entity by the anchor's device_id, so one entity is
// enough. Uses stock services only (switch/number/button) — no custom services.

const TAG = "reef-dose-card";

// Status-bottle colours, straight from the app's glossary.
const STOCK_COLORS = {
  high: "#22c55e", // green
  low: "#f59e0b", // orange
  empty: "#ef4444", // red
  no_auto_dose: "#2b7fff", // blue — automatic dosing off
};

// Per-head entity roles: suffix (after `head_<n>_`) -> friendly key.
const HEAD_ROLES = {
  dosed_today: "dosedToday",
  daily_target: "dailyTarget",
  doses_per_day: "dosesPerDay",
  remaining_days: "remainingDays",
  stock_level: "stockLevel",
  supplement: "supplement",
  next_dose: "nextDose",
  last_calibrated: "lastCalibrated",
  manual_dose: "manualDose",
  daily_dose: "dailyDose",
  container: "container",
  dose_now: "doseNow",
  schedule: "schedule",
  food_head: "foodHead",
  monitor: "monitor",
  priming: "priming",
};

// Device-level roles: entity_id substring -> friendly key (order: specific first).
const DEVICE_ROLES = [
  ["automatic_dosing", "automaticDosing", "switch"],
  ["dosing_delay", "dosingDelay", "number"],
  ["stock_alert_days", "stockDays", "number"],
  ["battery", "battery", "sensor"],
  ["refresh", "refresh", "button"],
];

class ReefDoseCard extends HTMLElement {
  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("reef-dose-card: set `entity` to any entity of your ReefDose");
    }
    this._config = config;
    // theme: "auto" (follow HA dark mode) | "light" | "dark"
    this._theme = config.theme || "auto";
    // settings: "drawer" (behind ⚙) | "inline" (always visible)
    this._settingsMode = config.settings === "inline" ? "inline" : "drawer";
    this._sig = null;
    this._update();
  }

  _isDark() {
    if (this._theme === "dark") return true;
    if (this._theme === "light") return false;
    return !!this._hass?.themes?.darkMode;
  }

  getCardSize() {
    return 4;
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  // HA can assign `hass` before `setConfig` (and vice versa) depending on how the
  // view builds the element — only proceed once both are present, whatever the
  // order, or the card lands as a red "Configuration error".
  _update() {
    if (!this._hass || !this._config) return;
    this._resolve();
    const sig = this._signature();
    if (sig !== this._sig) {
      this._sig = sig;
      this._render();
    }
  }

  // --- resolution ---------------------------------------------------------

  _resolve() {
    const hass = this._hass;
    const anchor = hass.entities?.[this._config.entity];
    this._deviceId = anchor?.device_id;
    const ids = this._deviceId
      ? Object.values(hass.entities)
          .filter((e) => e.device_id === this._deviceId)
          .map((e) => e.entity_id)
      : [this._config.entity];

    this._device = {};
    for (const [needle, key, domain] of DEVICE_ROLES) {
      const hit = ids.find(
        (id) => id.startsWith(domain + ".") && id.includes("_" + needle) && !/_head_\d/.test(id)
      );
      if (hit) this._device[key] = hit;
    }

    // Per-head: group by the `head_<n>_` marker, map suffix -> role.
    const heads = {};
    for (const id of ids) {
      const m = id.match(/_head_(\d+)_(.+)$/);
      if (!m) continue;
      const n = parseInt(m[1], 10);
      const role = HEAD_ROLES[m[2]];
      if (!role) continue;
      (heads[n] = heads[n] || {})[role] = id;
    }
    this._heads = heads;

    this._name =
      (this._deviceId && hass.devices?.[this._deviceId]?.name_by_user) ||
      hass.devices?.[this._deviceId]?.name ||
      "ReefDose";
  }

  _st(id) {
    return id ? this._hass.states[id] : undefined;
  }
  _val(id) {
    const s = this._st(id);
    return s ? s.state : undefined;
  }
  _num(id) {
    const v = parseFloat(this._val(id));
    return isNaN(v) ? null : v;
  }

  // Re-render only when something visible changed.
  _signature() {
    if (!this._heads) return "";
    const parts = [
      this._name,
      this._isDark() ? "d" : "l",
      this._settingsMode,
      this._val(this._device.automaticDosing),
      this._val(this._device.battery),
    ];
    for (const n of Object.keys(this._heads).sort()) {
      const h = this._heads[n];
      parts.push(
        n,
        this._val(h.supplement),
        this._val(h.dosedToday),
        this._val(h.dailyTarget),
        this._val(h.dosesPerDay),
        this._val(h.remainingDays),
        this._val(h.stockLevel),
        this._val(h.container),
        this._val(h.nextDose),
        this._val(h.schedule),
        this._val(h.foodHead),
        this._val(h.monitor),
        this._val(h.priming),
        this._val(h.manualDose),
        this._val(h.dailyDose)
      );
    }
    return parts.join("|");
  }

  // --- actions ------------------------------------------------------------

  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }
  _toggle(id) {
    if (!id) return;
    const on = this._val(id) === "on";
    this._call("switch", on ? "turn_off" : "turn_on", { entity_id: id });
  }
  _setNumber(id, value) {
    if (id != null && value != null && !isNaN(value)) {
      this._call("number", "set_value", { entity_id: id, value });
    }
  }
  _press(id) {
    if (id) this._call("button", "press", { entity_id: id });
  }

  // --- render -------------------------------------------------------------

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const autoOn = this._val(this._device.automaticDosing) !== "off";
    const battery = this._val(this._device.battery);
    const batteryLow = battery && battery !== "normal" && battery !== "unknown";

    const headNums = Object.keys(this._heads)
      .map((n) => parseInt(n, 10))
      .sort((a, b) => a - b);

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="card ${this._isDark() ? "dark" : ""}">
        <div class="head">
          <div class="title">
            <span class="dot ${autoOn ? "on" : "off"}"></span>
            <span class="name">${this._name}</span>
          </div>
          <div class="head-right">
            ${batteryLow ? `<span class="warn" title="RTC battery ${battery}">🪫</span>` : ""}
            <button class="power ${autoOn ? "on" : "off"}" id="power" title="Automatic dosing">
              ${autoOn ? "Dosing" : "Heads OFF"}
            </button>
          </div>
        </div>
        <div class="heads">
          ${headNums.map((n) => this._headRow(n)).join("")}
        </div>
      </div>`;

    this._wire(headNums);
  }

  _headRow(n) {
    const h = this._heads[n];
    const supp = this._val(h.supplement) || `Head ${n}`;
    const dosed = this._num(h.dosedToday) ?? 0;
    const target = this._num(h.dailyTarget) ?? 0;
    const doses = this._val(h.dosesPerDay) ?? "0";
    const days = this._val(h.remainingDays);
    const stock = this._val(h.stockLevel) || "no_auto_dose";
    const container = this._num(h.container);
    const schedOn = this._val(h.schedule) === "on";
    const priming = this._val(h.priming) === "on";
    const color = STOCK_COLORS[stock] || STOCK_COLORS.no_auto_dose;
    const pct = target > 0 ? Math.min(100, Math.round((dosed / target) * 100)) : 0;
    const nextRaw = this._val(h.nextDose);
    const next = nextRaw && !["unknown", "unavailable"].includes(nextRaw)
      ? new Date(nextRaw).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : "—";

    return `
      <div class="head-row" data-h="${n}">
        <div class="hr-top">
          <div class="supp">${supp}</div>
          <div class="bottle" style="--c:${color}" title="${stock.replace(/_/g, " ")}"></div>
        </div>
        <div class="hr-mid">
          <span class="dosed">${dosed}<span class="unit">ml</span></span>
          <span class="slash">/ ${target}ml</span>
          <span class="next">⏰ ${next}</span>
        </div>
        <div class="bar"><div class="fill" style="width:${pct}%"></div></div>
        <div class="chips">
          <span class="chip">💧 ${dosed} / ${doses} doses</span>
          ${days != null ? `<span class="chip" style="--cc:${color}">🔋 ${days} days</span>` : ""}
          ${container != null ? `<span class="chip">🧴 ${container}ml</span>` : ""}
        </div>
        <div class="actions">
          <button class="dose" data-a="dose" data-h="${n}">Dose ${this._num(h.manualDose) ?? 5}ml</button>
          <button class="tgl ${schedOn ? "on" : ""}" data-a="sched" data-h="${n}">
            ${schedOn ? "Schedule on" : "Schedule off"}
          </button>
          ${this._settingsMode === "drawer" ? `<button class="link" data-a="more" data-h="${n}">⚙</button>` : ""}
        </div>
        <div class="drawer" data-drawer="${n}" ${this._settingsMode === "inline" ? "" : "hidden"}>
          <label>Daily dose (ml)
            <input type="number" step="0.1" value="${this._num(h.dailyDose) ?? ""}" data-in="dailyDose" data-h="${n}">
          </label>
          <label>Manual dose (ml)
            <input type="number" step="0.1" value="${this._num(h.manualDose) ?? 5}" data-in="manualDose" data-h="${n}">
          </label>
          <label>Container (ml)
            <input type="number" step="1" value="${container ?? ""}" data-in="container" data-h="${n}">
          </label>
          <div class="drawer-tgls">
            <button class="tgl ${this._val(h.foodHead) === "on" ? "on" : ""}" data-a="food" data-h="${n}">🐠 Food head</button>
            <button class="tgl ${this._val(h.monitor) === "on" ? "on" : ""}" data-a="monitor" data-h="${n}">📊 Monitor</button>
            <button class="tgl ${this._val(h.priming) === "on" ? "on" : ""}" data-a="prime" data-h="${n}">🚰 ${priming ? "Priming…" : "Prime"}</button>
          </div>
        </div>
      </div>`;
  }

  _wire(headNums) {
    const root = this.shadowRoot;
    const power = root.getElementById("power");
    if (power) power.onclick = () => this._toggle(this._device.automaticDosing);

    root.querySelectorAll("button[data-a]").forEach((btn) => {
      const n = parseInt(btn.dataset.h, 10);
      const h = this._heads[n];
      const a = btn.dataset.a;
      btn.onclick = () => {
        if (a === "dose") this._press(h.doseNow);
        else if (a === "sched") this._toggle(h.schedule);
        else if (a === "food") this._toggle(h.foodHead);
        else if (a === "monitor") this._toggle(h.monitor);
        else if (a === "prime") this._toggle(h.priming);
        else if (a === "more") {
          const d = root.querySelector(`[data-drawer="${n}"]`);
          if (d) d.hidden = !d.hidden;
        }
      };
    });

    root.querySelectorAll("input[data-in]").forEach((inp) => {
      const n = parseInt(inp.dataset.h, 10);
      const h = this._heads[n];
      inp.onchange = () => {
        const v = parseFloat(inp.value);
        if (isNaN(v)) return;
        if (inp.dataset.in === "dailyDose") this._setNumber(h.dailyDose, v);
        else if (inp.dataset.in === "manualDose") this._setNumber(h.manualDose, v);
        else if (inp.dataset.in === "container") this._setNumber(h.container, v);
      };
    });
  }

  _css() {
    return `
      :host { --blue:#2b7fff; --ink:#1a1d26; --muted:#8b90a0; --line:#eceef3; --bg:#f4f5f8; }
      .card { background:#fff; border-radius:20px; padding:16px; color:var(--ink);
        font-family: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; box-shadow:0 6px 24px rgba(20,25,45,.08); }
      .head { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
      .title { display:flex; align-items:center; gap:10px; }
      .name { font-size:1.25rem; font-weight:800; letter-spacing:-.02em; }
      .dot { width:10px; height:10px; border-radius:50%; }
      .dot.on { background:var(--blue); box-shadow:0 0 0 4px rgba(43,127,255,.15); }
      .dot.off { background:#ef4444; box-shadow:0 0 0 4px rgba(239,68,68,.15); }
      .head-right { display:flex; align-items:center; gap:10px; }
      .warn { font-size:1.1rem; }
      .power { border:none; border-radius:999px; padding:8px 16px; font-weight:700; cursor:pointer; font-size:.85rem; }
      .power.on { background:rgba(43,127,255,.12); color:var(--blue); }
      .power.off { background:rgba(239,68,68,.12); color:#ef4444; }
      .heads { display:flex; flex-direction:column; gap:12px; }
      .head-row { border:1px solid var(--line); border-radius:16px; padding:14px; }
      .hr-top { display:flex; align-items:center; justify-content:space-between; }
      .supp { font-weight:800; font-size:1.05rem; }
      .bottle { width:16px; height:24px; border-radius:4px 4px 5px 5px; background:var(--c);
        position:relative; box-shadow:inset 0 0 0 2px rgba(0,0,0,.06); }
      .bottle::before { content:""; position:absolute; top:-5px; left:4px; right:4px; height:5px;
        background:var(--c); border-radius:2px 2px 0 0; }
      .hr-mid { display:flex; align-items:baseline; gap:8px; margin:8px 0 6px; }
      .dosed { font-size:1.5rem; font-weight:800; letter-spacing:-.03em; }
      .unit { font-size:.85rem; font-weight:600; color:var(--muted); margin-left:1px; }
      .slash { color:var(--muted); font-weight:600; }
      .next { margin-left:auto; color:var(--muted); font-size:.85rem; font-weight:600; }
      .bar { height:7px; border-radius:99px; background:var(--bg); overflow:hidden; }
      .fill { height:100%; background:var(--blue); border-radius:99px; transition:width .4s ease; }
      .chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
      .chip { background:var(--bg); border-radius:10px; padding:6px 10px; font-size:.8rem; font-weight:600; color:#41465a; }
      .actions { display:flex; gap:8px; margin-top:12px; align-items:center; }
      .dose { background:var(--blue); color:#fff; border:none; border-radius:12px; padding:10px 16px;
        font-weight:700; cursor:pointer; flex:1; font-size:.9rem; }
      .dose:hover { filter:brightness(1.05); }
      .tgl { background:#fff; border:1.5px solid var(--line); border-radius:12px; padding:9px 12px;
        font-weight:700; cursor:pointer; color:var(--muted); font-size:.82rem; }
      .tgl.on { border-color:var(--blue); color:var(--blue); background:rgba(43,127,255,.06); }
      .link { background:none; border:none; cursor:pointer; font-size:1.1rem; padding:6px; color:var(--muted); }
      .drawer { margin-top:12px; padding-top:12px; border-top:1px dashed var(--line);
        display:grid; grid-template-columns:1fr 1fr; gap:10px; }
      .drawer label { display:flex; flex-direction:column; gap:4px; font-size:.75rem; font-weight:700; color:var(--muted); }
      .drawer input { border:1.5px solid var(--line); border-radius:10px; padding:8px; font-size:.95rem; font-weight:600; }
      .drawer input:focus { outline:none; border-color:var(--blue); }
      .drawer-tgls { grid-column:1 / -1; display:flex; gap:8px; flex-wrap:wrap; }

      /* --- dark theme (matched to ReefBeat: charcoal blocks on near-black, blue accent) --- */
      .card.dark { --ink:#f4f6f8; --muted:#9aa0a8; --line:#363a42; --bg:#34383f; --blue:#2f7bf6;
        background:#1b1d21; box-shadow:0 12px 32px rgba(0,0,0,.55); }
      .card.dark .head-row { background:#2b2e34; border-color:#363a42; }
      .card.dark .chip { background:#34383f; color:#c8cdd6; }
      .card.dark .bar { background:#45494f; }
      .card.dark .tgl { background:#2b2e34; border-color:#3d414a; color:#9aa0a8; }
      .card.dark .tgl.on { background:rgba(47,123,246,.16); border-color:var(--blue); color:#8bb6ff; }
      .card.dark .power.on { background:rgba(47,123,246,.18); color:#8bb6ff; }
      .card.dark .power.off { background:rgba(229,72,77,.20); color:#ff8589; }
      .card.dark .drawer { border-top-color:#363a42; }
      .card.dark .drawer input { background:#24272d; border-color:#3d414a; color:var(--ink); }
      .card.dark .link.active { color:#8bb6ff; }
    `;
  }
}

// Some setups load a scoped-custom-element-registry polyfill (bundled by other
// cards, e.g. universal-remote-card) that replaces window.customElements AFTER
// we run, orphaning our early definition. Re-assert it across load phases — a
// fresh subclass each time dodges "constructor already used" — so whichever
// registry HA ends up querying has the element (mirrors the RF card).
const rdDefine = () => {
  if (customElements.get(TAG)) return;
  try {
    customElements.define(TAG, class extends ReefDoseCard {});
  } catch (_) {
    /* already defined in this registry */
  }
};
rdDefine();
window.addEventListener("load", rdDefine);
setTimeout(rdDefine, 1500);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === TAG)) {
  window.customCards.push({
    type: TAG,
    name: "Red Sea ReefDose",
    description: "Per-head dosing control for a Red Sea ReefDose (Multi Reef).",
  });
}
