// Multi Reef — Red Sea ReefDose card.
//
// Modelled on the ReefBeat home card: a minimal surface — device name, a status
// icon cluster, and one slim row per head (supplement · dosed/target · progress
// bar with the purple manual "+Nml" overshoot · stock bottle). Everything else
// (dose now, schedule, amounts, calibration-ish toggles) stays hidden until you
// tap a head row.
//
// Config:  type: custom:reef-dose-card
//          entity: <any entity of the ReefDose device>   (used to find siblings)
//          theme: auto | light | dark        (auto follows the HA theme)
//          settings: drawer | inline         (inline = head details start open)
//
// Uses stock services only (switch/number/button) — no custom services.

const TAG = "reef-dose-card";

// Status-bottle colours, straight from the app's glossary.
const STOCK_COLORS = {
  high: "#22c55e", // green
  low: "#f4b312", // amber
  empty: "#ef4444", // red
  no_auto_dose: "#2f7bf6", // blue — automatic dosing off
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

// Device-level roles: entity_id substring -> friendly key.
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
    // settings: "inline" -> head details start expanded; "drawer" -> collapsed
    this._startOpen = config.settings === "inline";
    this._open = this._open || new Set();
    this._sig = null;
    this._update();
  }

  _isDark() {
    if (this._theme === "dark") return true;
    if (this._theme === "light") return false;
    return !!this._hass?.themes?.darkMode;
  }

  getCardSize() {
    return 3;
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

    if (this._startOpen && !this._openInit) {
      this._openInit = true;
      Object.keys(heads).forEach((n) => this._open.add(Number(n)));
    }

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
  _attr(id, name) {
    const s = this._st(id);
    const v = s ? parseFloat(s.attributes?.[name]) : NaN;
    return isNaN(v) ? null : v;
  }

  _signature() {
    if (!this._heads) return "";
    const parts = [
      this._name,
      this._isDark() ? "d" : "l",
      this._val(this._device.automaticDosing),
      this._val(this._device.battery),
    ];
    for (const n of Object.keys(this._heads).sort()) {
      const h = this._heads[n];
      parts.push(
        n,
        this._val(h.supplement),
        this._val(h.dosedToday),
        this._attr(h.dosedToday, "auto_ml"),
        this._attr(h.dosedToday, "manual_ml"),
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
    const headsOn = this._val(this._device.automaticDosing) !== "off";
    const battery = this._val(this._device.battery);
    const batteryLow = battery && battery !== "normal" && battery !== "unknown" && battery !== "unavailable";

    const headNums = Object.keys(this._heads)
      .map((n) => parseInt(n, 10))
      .sort((a, b) => a - b);

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="card ${this._isDark() ? "dark" : ""}">
        <div class="head">
          <div class="name">${this._esc(this._name)}</div>
          <div class="icons">
            <span class="chip" title="Connected"><ha-icon icon="mdi:wifi"></ha-icon></span>
            ${batteryLow ? `<span class="batt" title="Backup battery ${this._esc(battery)}"><ha-icon icon="mdi:battery-remove-outline"></ha-icon></span>` : ""}
            <button class="pwr ${headsOn ? "" : "off"}" id="power"
              title="${headsOn ? "Automatic dosing on — click to switch heads off" : "Heads OFF — click to resume dosing"}">
              <ha-icon icon="mdi:power"></ha-icon>
            </button>
          </div>
        </div>
        ${headsOn ? "" : `<div class="offline">Head/s OFF</div>`}
        <div class="heads">
          ${headNums.map((n) => this._headRow(n)).join("")}
        </div>
      </div>`;

    this._wire(headNums);
  }

  _headRow(n) {
    const h = this._heads[n];
    const supp = this._val(h.supplement) || `Head ${n}`;
    const target = this._num(h.dailyTarget) ?? 0;
    const total = this._num(h.dosedToday) ?? 0;
    let auto = this._attr(h.dosedToday, "auto_ml");
    let manual = this._attr(h.dosedToday, "manual_ml");
    if (auto == null) auto = total; // older integration: no split available
    if (manual == null) manual = 0;
    const stock = this._val(h.stockLevel) || "no_auto_dose";
    const color = STOCK_COLORS[stock] || STOCK_COLORS.no_auto_dose;
    const pct = target > 0 ? Math.min(100, Math.round((auto / target) * 100)) : 0;
    const open = this._open.has(n);

    const schedOn = this._val(h.schedule) === "on";
    const doses = this._val(h.dosesPerDay) ?? "0";
    const days = this._val(h.remainingDays);
    const container = this._num(h.container);
    const nextRaw = this._val(h.nextDose);
    const next =
      nextRaw && !["unknown", "unavailable"].includes(nextRaw)
        ? new Date(nextRaw).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : "—";

    return `
      <div class="row" data-h="${n}">
        <div class="hr" data-toggle="${n}" role="button" aria-expanded="${open}">
          <div class="main">
            <div class="line1">
              <span class="supp">${this._esc(supp)}</span>
              <span class="amounts"><b>${auto}</b><i>ml</i><em>/ ${target}ml</em></span>
            </div>
            <div class="bar">
              <div class="auto" style="width:${pct}%"></div>
              ${manual > 0 ? `<div class="manual"></div>` : ""}
            </div>
            ${manual > 0 ? `<div class="plus">+${manual}ml</div>` : ""}
          </div>
          <div class="bottle" style="--c:${color}" title="${this._esc(stock.replace(/_/g, " "))}"></div>
        </div>
        <div class="detail" data-detail="${n}" ${open ? "" : "hidden"}>
          <div class="chips">
            <span class="c">⏰ ${next}</span>
            <span class="c">💧 ${doses}/day</span>
            ${days != null ? `<span class="c">🔋 ${days} days</span>` : ""}
            ${container != null ? `<span class="c">🧴 ${container}ml</span>` : ""}
          </div>
          <div class="actions">
            <button class="dose" data-a="dose" data-h="${n}">Dose ${this._num(h.manualDose) ?? 5}ml</button>
            <button class="tgl ${schedOn ? "on" : ""}" data-a="sched" data-h="${n}">${schedOn ? "Schedule on" : "Schedule off"}</button>
          </div>
          <div class="inputs">
            <label>Daily dose (ml)<input type="number" step="0.1" value="${this._num(h.dailyDose) ?? ""}" data-in="dailyDose" data-h="${n}"></label>
            <label>Manual dose (ml)<input type="number" step="0.1" value="${this._num(h.manualDose) ?? 5}" data-in="manualDose" data-h="${n}"></label>
            <label>Container (ml)<input type="number" step="1" value="${container ?? ""}" data-in="container" data-h="${n}"></label>
          </div>
          <div class="minor">
            <button class="tgl ${this._val(h.foodHead) === "on" ? "on" : ""}" data-a="food" data-h="${n}">🐠 Food head</button>
            <button class="tgl ${this._val(h.monitor) === "on" ? "on" : ""}" data-a="monitor" data-h="${n}">📊 Monitor</button>
            <button class="tgl ${this._val(h.priming) === "on" ? "on" : ""}" data-a="prime" data-h="${n}">🚰 Prime</button>
          </div>
        </div>
      </div>`;
  }

  _wire(headNums) {
    const root = this.shadowRoot;
    const power = root.getElementById("power");
    if (power) power.onclick = () => this._toggle(this._device.automaticDosing);

    root.querySelectorAll("[data-toggle]").forEach((row) => {
      row.onclick = () => {
        const n = parseInt(row.dataset.toggle, 10);
        const det = root.querySelector(`[data-detail="${n}"]`);
        if (!det) return;
        if (this._open.has(n)) {
          this._open.delete(n);
          det.hidden = true;
          row.setAttribute("aria-expanded", "false");
        } else {
          this._open.add(n);
          det.hidden = false;
          row.setAttribute("aria-expanded", "true");
        }
      };
    });

    root.querySelectorAll("button[data-a]").forEach((btn) => {
      const n = parseInt(btn.dataset.h, 10);
      const h = this._heads[n];
      const a = btn.dataset.a;
      btn.onclick = (e) => {
        e.stopPropagation();
        if (a === "dose") this._press(h.doseNow);
        else if (a === "sched") this._toggle(h.schedule);
        else if (a === "food") this._toggle(h.foodHead);
        else if (a === "monitor") this._toggle(h.monitor);
        else if (a === "prime") this._toggle(h.priming);
      };
    });

    root.querySelectorAll("input[data-in]").forEach((inp) => {
      const n = parseInt(inp.dataset.h, 10);
      const h = this._heads[n];
      inp.onclick = (e) => e.stopPropagation();
      inp.onchange = () => {
        const v = parseFloat(inp.value);
        if (isNaN(v)) return;
        if (inp.dataset.in === "dailyDose") this._setNumber(h.dailyDose, v);
        else if (inp.dataset.in === "manualDose") this._setNumber(h.manualDose, v);
        else if (inp.dataset.in === "container") this._setNumber(h.container, v);
      };
    });
  }

  _esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }

  _css() {
    return `
      :host { --blue:#2b7fff; --purple:#c05cf7; --ink:#1a1d26; --muted:#8b90a0;
              --track:#e8eaef; --chipbg:#f4f5f8; --line:#eceef3; }
      /* Our display rules would otherwise beat the UA's [hidden] handling and
         leave every head's detail permanently expanded. */
      [hidden] { display:none !important; }
      .card { background:#fff; border-radius:24px; padding:20px 22px; color:var(--ink);
        font-family: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
        box-shadow:0 8px 28px rgba(20,25,45,.10); }
      .head { display:flex; align-items:flex-start; justify-content:space-between; }
      .name { font-size:1.45rem; font-weight:800; letter-spacing:-.02em; }
      .icons { display:flex; flex-direction:column; align-items:flex-end; gap:8px; }
      .chip { width:38px; height:38px; border-radius:50%; background:var(--chipbg);
        display:flex; align-items:center; justify-content:center; color:var(--ink); }
      .chip ha-icon, .batt ha-icon, .pwr ha-icon { --mdc-icon-size:20px; }
      .batt { color:#ef4444; }
      .pwr { background:none; border:none; cursor:pointer; padding:2px; color:var(--muted); }
      .pwr.off { color:#ef4444; }
      .offline { color:#ef4444; font-weight:800; margin:4px 0 0; }
      .heads { display:flex; flex-direction:column; gap:20px; margin-top:18px; }
      .row {}
      .hr { display:flex; align-items:center; gap:14px; cursor:pointer; }
      .main { flex:1; min-width:0; }
      .line1 { display:flex; align-items:baseline; justify-content:space-between; gap:10px; }
      .supp { font-size:1.15rem; font-weight:600; }
      .amounts b { font-size:1.5rem; font-weight:800; letter-spacing:-.02em;
        font-variant-numeric:tabular-nums; }
      .amounts i { font-style:normal; font-size:.85rem; font-weight:600; color:var(--muted); }
      .amounts em { font-style:normal; font-size:.95rem; font-weight:600; color:var(--muted); margin-left:2px; }
      .bar { position:relative; height:9px; border-radius:99px; background:var(--track);
        overflow:hidden; margin-top:8px; }
      .auto { position:absolute; left:0; top:0; bottom:0; background:var(--blue); border-radius:99px;
        transition:width .4s ease; }
      .manual { position:absolute; right:0; top:0; bottom:0; width:21%; background:var(--purple);
        border-radius:99px; box-shadow:-3px 0 0 0 var(--track); }
      .plus { text-align:right; color:var(--purple); font-weight:700; font-size:.9rem; margin-top:4px; }
      .bottle { width:17px; height:26px; border-radius:4px 4px 5px 5px; background:var(--c);
        position:relative; flex:0 0 auto; box-shadow:inset 0 0 0 2px rgba(0,0,0,.08); }
      .bottle::before { content:""; position:absolute; top:-5px; left:4px; right:4px; height:5px;
        background:var(--c); border-radius:2px 2px 0 0; }
      .detail { margin-top:12px; padding:14px; border-radius:14px; background:var(--chipbg);
        display:flex; flex-direction:column; gap:12px; }
      .chips { display:flex; flex-wrap:wrap; gap:8px; }
      .c { background:#fff; border-radius:10px; padding:6px 10px; font-size:.8rem; font-weight:600; color:#41465a; }
      .actions { display:flex; gap:8px; }
      .dose { background:var(--blue); color:#fff; border:none; border-radius:12px; padding:10px 16px;
        font-weight:700; cursor:pointer; flex:1; font-size:.9rem; }
      .dose:hover { filter:brightness(1.05); }
      .tgl { background:#fff; border:1.5px solid var(--line); border-radius:12px; padding:9px 12px;
        font-weight:700; cursor:pointer; color:var(--muted); font-size:.82rem; }
      .tgl.on { border-color:var(--blue); color:var(--blue); background:rgba(43,127,255,.06); }
      .inputs { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
      .inputs label { display:flex; flex-direction:column; gap:4px; font-size:.72rem; font-weight:700; color:var(--muted); }
      .inputs input { border:1.5px solid var(--line); border-radius:10px; padding:8px; font-size:.95rem;
        font-weight:600; font-family:inherit; min-width:0; background:#fff; color:var(--ink); }
      .inputs input:focus { outline:none; border-color:var(--blue); }
      .minor { display:flex; gap:8px; flex-wrap:wrap; }
      @media (max-width:420px) { .inputs { grid-template-columns:1fr 1fr; } }

      /* --- dark: matched to the ReefBeat home card --- */
      .card.dark { --ink:#f4f6f8; --muted:#9aa0a8; --track:#5a5e66; --chipbg:#34383f;
        --line:#3d414a; --blue:#2f7bf6; background:#2b2e34;
        box-shadow:0 12px 32px rgba(0,0,0,.5); }
      .card.dark .chip { background:#3a3e46; color:#fff; }
      .card.dark .c { background:#2b2e34; color:#c8cdd6; }
      .card.dark .tgl { background:#2b2e34; }
      .card.dark .tgl.on { background:rgba(47,123,246,.16); color:#8bb6ff; }
      .card.dark .inputs input { background:#24272d; }
      .card.dark .detail { background:#24272d; }
      .card.dark .manual { box-shadow:-3px 0 0 0 #2b2e34; }
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
