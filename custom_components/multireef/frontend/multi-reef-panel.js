/*
 * Multi Reef — sidebar panel / config engine.
 *
 * Registered by the multireef integration as a custom panel. It discovers
 * supported reef devices and provisions their purpose-built cards onto the user's
 * real dashboards — pick a device, pick a dashboard + view, and it writes the card
 * in, pre-linked, with no copy-paste.
 *
 * Vendor-agnostic by design: the CATALOG below is the only brand-aware surface.
 * Each brand adds one entry (how to detect its device + which card to place); the
 * panel core knows nothing else specific. First release ships the RF doser only.
 */

// ---- catalog: the one brand-aware surface -------------------------------------
// detect: a device is provisionable if it owns an entity in `anchorDomain` whose
// entity_id contains `anchorKeyword`. That anchor entity becomes the card's
// `entity` — our cards self-resolve their siblings from it.
const CATALOG = [
  {
    id: "rf-doser",
    brand: "Reef Factory",
    name: "Single-Head Doser",
    icon: "mdi:water-pump",
    cardType: "custom:reef-factory-doser-card",
    anchorDomain: "sensor",
    anchorKeyword: "container_level",
    cardOptions: { grid_options: { columns: "full", rows: 8 } },
  },
  {
    id: "redsea-dose",
    brand: "Red Sea",
    name: "ReefDose",
    icon: "mdi:water-plus",
    cardType: "custom:reef-dose-card",
    anchorDomain: "sensor",
    // "head_1_" is unique to ReefDose entities (the RF doser also has a
    // dosed_today sensor, so the head marker keeps the match unambiguous).
    anchorKeyword: "head_1_dosed_today",
    cardOptions: { grid_options: { columns: "full", rows: 8 } },
    // Style choices offered in the add-card dialog; each becomes a key in the
    // card config. First option is the default. (No theme choice — the card is
    // an ha-card, so it follows the dashboard theme like every Multi Reef card.)
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
];

const BLUE = "#3f8fd6";

class MultiReefPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._renderDevices();
    this._renderBridges();
  }
  set narrow(v) {
    this._narrow = v;
  }
  set route(v) {
    this._route = v;
  }
  set panel(v) {
    this._panel = v;
  }

  $(id) {
    return this._root.getElementById(id);
  }

  // ---- device discovery -------------------------------------------------------
  _discover() {
    const hass = this._hass;
    if (!hass) return [];
    const seen = new Set();
    const devices = [];
    for (const entry of CATALOG) {
      for (const entity_id of Object.keys(hass.states)) {
        if (!entity_id.startsWith(entry.anchorDomain + ".")) continue;
        if (!entity_id.toLowerCase().includes(entry.anchorKeyword)) continue;
        const reg = hass.entities?.[entity_id];
        const deviceId = reg?.device_id || entity_id; // fall back to entity as key
        const key = `${entry.id}:${deviceId}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const dev = deviceId && hass.devices ? hass.devices[deviceId] : undefined;
        devices.push({
          entry,
          deviceId,
          anchorEntity: entity_id,
          name: (dev && (dev.name_by_user || dev.name)) || entry.name,
        });
      }
    }
    return devices;
  }

  // ---- structure (built once) -------------------------------------------------
  _build() {
    this._built = true;
    this._root = this.attachShadow({ mode: "open" });
    this._root.innerHTML = `
      <style>
        :host { --mr-blue:${BLUE}; display:block; height:100%;
                background:var(--primary-background-color); color:var(--primary-text-color); }
        .wrap { max-width:960px; margin:0 auto; padding:24px 20px 64px; }
        header.hero { display:flex; align-items:center; gap:14px; margin:8px 0 28px; }
        .logo { width:44px; height:44px; border-radius:12px; flex:0 0 auto;
                background:linear-gradient(135deg,var(--mr-blue),#2b6fb0);
                display:flex; align-items:center; justify-content:center; }
        .logo ha-icon { --mdc-icon-size:26px; color:#fff; }
        .hero h1 { margin:0; font-size:1.5rem; font-weight:600; letter-spacing:-.01em; }
        .hero p { margin:2px 0 0; color:var(--secondary-text-color); font-size:.9rem; }
        .sec-label { text-transform:uppercase; letter-spacing:.08em; font-size:.72rem;
                     color:var(--secondary-text-color); margin:26px 4px 12px; font-weight:600; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }
        .dev { background:var(--card-background-color,#1c1f24); border:1px solid var(--divider-color,#333);
               border-radius:14px; padding:16px; display:flex; flex-direction:column; gap:12px;
               transition:border-color .15s ease, transform .1s ease; }
        .dev:hover { border-color:var(--mr-blue); }
        .dev .top { display:flex; align-items:center; gap:12px; }
        .dev .ic { width:40px; height:40px; border-radius:10px; flex:0 0 auto;
                   background:color-mix(in srgb,var(--mr-blue) 16%, transparent);
                   display:flex; align-items:center; justify-content:center; }
        .dev .ic ha-icon { --mdc-icon-size:22px; color:var(--mr-blue); }
        .dev .name { font-weight:600; font-size:1rem; line-height:1.2; }
        .dev .brand { color:var(--secondary-text-color); font-size:.8rem; margin-top:1px; }
        .dev .anchor { color:var(--secondary-text-color); font-size:.74rem; font-family:monospace;
                       overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .btn { background:var(--mr-blue); color:#fff; border:none; border-radius:8px; padding:10px 14px;
               font-size:.88rem; font-weight:500; cursor:pointer; transition:filter .15s ease, transform .08s ease; }
        .btn:hover { filter:brightness(1.08); } .btn:active { transform:translateY(1px); }
        .btn.ghost { background:transparent; color:var(--mr-blue); border:1px solid var(--mr-blue); }
        .btn[disabled] { opacity:.5; cursor:default; filter:none; transform:none; }
        .empty { border:1px dashed var(--divider-color,#444); border-radius:14px; padding:34px 20px;
                 text-align:center; color:var(--secondary-text-color); }
        .empty ha-icon { --mdc-icon-size:34px; color:var(--secondary-text-color); opacity:.6; }
        .empty p { margin:10px 0 0; font-size:.9rem; }
        .support { display:flex; flex-wrap:wrap; gap:8px; }
        .chip { display:inline-flex; align-items:center; gap:6px; font-size:.8rem;
                border:1px solid var(--divider-color,#444); border-radius:999px; padding:5px 11px;
                color:var(--secondary-text-color); }
        .chip ha-icon { --mdc-icon-size:16px; }
        .chip.on { color:var(--mr-blue); border-color:var(--mr-blue); }
        /* modal */
        .modal { position:fixed; inset:0; background:rgba(0,0,0,.55); display:flex;
                 align-items:center; justify-content:center; z-index:9; padding:16px; }
        .dialog { background:var(--ha-card-background,var(--card-background-color,#1f2226));
                  border-radius:14px; padding:22px; width:min(94vw,440px); box-shadow:0 16px 50px rgba(0,0,0,.5); }
        .dialog h3 { margin:0 0 4px; font-size:1.15rem; }
        .dialog .sub { color:var(--secondary-text-color); font-size:.85rem; margin:0 0 16px; }
        label { display:block; font-size:.74rem; text-transform:uppercase; letter-spacing:.05em;
                color:var(--secondary-text-color); margin:12px 0 5px; }
        select { width:100%; box-sizing:border-box; padding:10px; border-radius:8px;
                 border:1px solid var(--divider-color,#555); font-size:.95rem;
                 background:var(--primary-background-color,#111); color:var(--primary-text-color); }
        .row { display:flex; gap:10px; margin-top:20px; } .row .btn { flex:1; }
        .status { margin-top:14px; font-size:.85rem; min-height:1.2em; }
        .status.ok { color:var(--success-color,#3fae5a); }
        .status.err { color:var(--error-color,#e2574c); }
        .status.warn { color:var(--warning-color,#e5a33d); }
      </style>
      <div class="wrap">
        <header class="hero">
          <div class="logo"><ha-icon icon="mdi:fishbowl-outline"></ha-icon></div>
          <div>
            <h1>Multi Reef</h1>
            <p>Set up your reef devices and drop their cards onto any dashboard — wired up, no YAML.</p>
          </div>
        </header>

        <div class="sec-label">Your devices</div>
        <div id="devices" class="grid"></div>

        <div class="sec-label" id="bridges-label" style="display:none">Bridges</div>
        <div id="bridges" class="grid"></div>

        <div class="sec-label">Supported devices</div>
        <div id="support" class="support"></div>
      </div>
      <div id="modalHost"></div>
    `;
    this._renderSupport();
  }

  _renderSupport() {
    const host = this.$("support");
    host.innerHTML = CATALOG.map(
      (c) => `<span class="chip"><ha-icon icon="${c.icon}"></ha-icon>${c.brand} · ${c.name}</span>`
    ).join("");
  }

  _renderDevices() {
    const host = this.$("devices");
    if (!host) return;
    const devices = this._discover();
    // avoid needless DOM churn — only re-render when the device set changes
    const sig = devices.map((d) => d.deviceId + "|" + d.anchorEntity).join(",");
    if (sig === this._devSig) return;
    this._devSig = sig;
    this._devices = devices;

    if (!devices.length) {
      host.className = "";
      host.innerHTML = `
        <div class="empty">
          <ha-icon icon="mdi:magnify-scan"></ha-icon>
          <p>No supported reef devices found yet. Add one in Settings → Devices &amp; Services and it will appear here.</p>
        </div>`;
      return;
    }
    host.className = "grid";
    host.innerHTML = devices
      .map(
        (d, i) => `
        <div class="dev">
          <div class="top">
            <div class="ic"><ha-icon icon="${d.entry.icon}"></ha-icon></div>
            <div style="min-width:0">
              <div class="name">${this._esc(d.name)}</div>
              <div class="brand">${d.entry.brand} · ${d.entry.name}</div>
            </div>
          </div>
          <div class="anchor" title="${d.anchorEntity}">${d.anchorEntity}</div>
          <button class="btn" data-i="${i}">Add card to dashboard</button>
        </div>`
      )
      .join("");
    host.querySelectorAll("button[data-i]").forEach((b) => {
      b.onclick = () => this._openDialog(this._devices[Number(b.dataset.i)]);
    });
  }

  // ---- bridges: firmware over-the-air ----------------------------------------
  // Surfaces the integration's bridge `update.*` entities so a firmware update is
  // one click here, not a CLI command.
  _findBridges() {
    const hass = this._hass;
    if (!hass) return [];
    const out = [];
    for (const entity_id of Object.keys(hass.states)) {
      if (!entity_id.startsWith("update.")) continue;
      const reg = hass.entities?.[entity_id];
      if (!reg || reg.platform !== "multireef") continue;
      const st = hass.states[entity_id];
      const dev = reg.device_id && hass.devices ? hass.devices[reg.device_id] : undefined;
      out.push({
        entity_id,
        name: (dev && (dev.name_by_user || dev.name)) || "Multi Reef Bridge",
        installed: st.attributes.installed_version,
        latest: st.attributes.latest_version,
        updateAvailable: st.state === "on",
        inProgress: !!st.attributes.in_progress,
      });
    }
    return out;
  }

  _renderBridges() {
    const host = this.$("bridges");
    const label = this.$("bridges-label");
    if (!host) return;
    const bridges = this._findBridges();
    const sig = bridges
      .map((b) => [b.entity_id, b.installed, b.latest, b.updateAvailable, b.inProgress].join("|"))
      .join(",");
    if (sig === this._brSig) return;
    this._brSig = sig;
    this._bridges = bridges;
    if (!bridges.length) {
      host.innerHTML = "";
      if (label) label.style.display = "none";
      return;
    }
    if (label) label.style.display = "";
    host.innerHTML = bridges
      .map(
        (b, i) => `
        <div class="dev">
          <div class="top">
            <div class="ic"><ha-icon icon="mdi:access-point"></ha-icon></div>
            <div style="min-width:0">
              <div class="name">${this._esc(b.name)}</div>
              <div class="brand">Firmware ${this._esc(b.installed || "?")}${
          b.updateAvailable ? " → " + this._esc(b.latest) : ""
        }</div>
            </div>
          </div>
          <button class="btn${b.updateAvailable ? "" : " ghost"}" data-b="${i}" ${
          b.updateAvailable && !b.inProgress ? "" : "disabled"
        }>${b.inProgress ? "Updating…" : b.updateAvailable ? "Update firmware" : "Up to date"}</button>
        </div>`
      )
      .join("");
    host.querySelectorAll("button[data-b]").forEach((btn) => {
      btn.onclick = () => this._updateBridge(this._bridges[Number(btn.dataset.b)]);
    });
  }

  async _updateBridge(b) {
    if (!b || !b.updateAvailable || b.inProgress) return;
    try {
      await this._hass.callService("update", "install", { entity_id: b.entity_id });
      this._brSig = null; // let the next hass push reflect "Updating…"
    } catch (e) {
      /* HA surfaces the error toast */
    }
  }

  // ---- provisioning dialog ----------------------------------------------------
  async _openDialog(device) {
    const host = this.$("modalHost");
    host.innerHTML = `
      <div class="modal" id="ov">
        <div class="dialog">
          <h3>Add ${this._esc(device.entry.name)} card</h3>
          <p class="sub">${this._esc(device.name)} → choose where it goes.</p>
          <label>Dashboard</label>
          <select id="dash"><option>Loading…</option></select>
          <label>View</label>
          <select id="view"><option>—</option></select>
          ${(device.entry.variants || [])
            .map(
              (v) => `
          <label>${this._esc(v.label)}</label>
          <select id="var-${this._esc(v.key)}">${v.options
            .map(([val, text]) => `<option value="${this._esc(val)}">${this._esc(text)}</option>`)
            .join("")}</select>`
            )
            .join("")}
          <div class="status" id="st"></div>
          <div class="row">
            <button class="btn ghost" id="cancel">Cancel</button>
            <button class="btn" id="add" disabled>Add card</button>
          </div>
        </div>
      </div>`;
    this.$("ov").onclick = (e) => {
      if (e.target.id === "ov") this._closeDialog();
    };
    this.$("cancel").onclick = () => this._closeDialog();

    const dashSel = this.$("dash");
    const viewSel = this.$("view");
    const addBtn = this.$("add");

    let dashboards = [];
    try {
      dashboards = await this._loadDashboards();
    } catch (e) {
      this._status("err", "Couldn't load dashboards.");
      return;
    }
    dashSel.innerHTML = dashboards
      .map((d, i) => `<option value="${i}">${this._esc(d.title)}</option>`)
      .join("");

    const loadViews = async () => {
      viewSel.innerHTML = `<option>Loading…</option>`;
      addBtn.disabled = true;
      this._status("", "");
      const dash = dashboards[Number(dashSel.value)];
      try {
        const cfg = await this._hass.callWS({
          type: "lovelace/config",
          url_path: dash.url_path,
        });
        this._activeCfg = cfg;
        const views = cfg.views || [];
        if (cfg.strategy || !views.length) {
          viewSel.innerHTML = `<option>—</option>`;
          this._status("warn", "Auto-generated dashboard — open it and “Take control” first.");
          return;
        }
        viewSel.innerHTML = views
          .map(
            (v, i) =>
              `<option value="${i}">${this._esc(v.title || v.path || "View " + (i + 1))}</option>`
          )
          .join("");
        this._maybeEnable(device);
      } catch (e) {
        viewSel.innerHTML = `<option>—</option>`;
        this._status("err", "Couldn't read that dashboard (it may be in YAML mode).");
      }
    };

    dashSel.onchange = loadViews;
    viewSel.onchange = () => this._maybeEnable(device);
    addBtn.onclick = () => this._provision(device, dashboards[Number(dashSel.value)]);
    await loadViews();
  }

  _maybeEnable(device) {
    const viewSel = this.$("view");
    const addBtn = this.$("add");
    const cfg = this._activeCfg;
    const vi = Number(viewSel.value);
    const view = cfg?.views?.[vi];
    if (!view || (!Array.isArray(view.sections) && !Array.isArray(view.cards))) {
      addBtn.disabled = true;
      return;
    }
    if (this._alreadyHas(view, device)) {
      addBtn.disabled = true;
      this._status("warn", "This device's card is already on that view.");
    } else {
      addBtn.disabled = false;
      this._status("", "");
    }
  }

  async _provision(device, dash) {
    const addBtn = this.$("add");
    addBtn.disabled = true;
    this._status("", "Adding…");
    const cfg = this._activeCfg;
    const view = cfg.views[Number(this.$("view").value)];
    const card = { type: device.entry.cardType, entity: device.anchorEntity, ...(device.entry.cardOptions || {}) };
    // Fold in the chosen style variants (theme, settings layout, …).
    for (const v of device.entry.variants || []) {
      const sel = this.$(`var-${v.key}`);
      if (sel && sel.value) card[v.key] = sel.value;
    }
    if (!this._appendCard(view, card)) {
      this._status("err", "That view can't take a card (auto-generated layout).");
      return;
    }
    try {
      await this._hass.callWS({ type: "lovelace/config/save", url_path: dash.url_path, config: cfg });
      const where = dash.title + " → " + (view.title || view.path || "view");
      this._status("ok", "Added to " + where + ".");
      this._devSig = null; // allow list refresh
      setTimeout(() => this._closeDialog(), 1100);
    } catch (e) {
      this._status("err", "Save failed: " + (e?.message || "unknown error"));
      addBtn.disabled = false;
    }
  }

  // ---- dashboard/view helpers -------------------------------------------------
  async _loadDashboards() {
    let list = [];
    try {
      list = await this._hass.callWS({ type: "lovelace/dashboards/list" });
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

  _appendCard(view, card) {
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

  _alreadyHas(view, device) {
    const match = (c) =>
      c && c.type === device.entry.cardType && c.entity === device.anchorEntity;
    const scan = (cards) =>
      Array.isArray(cards) &&
      cards.some((c) => match(c) || scan(c?.cards) || (c?.sections || []).some((s) => scan(s.cards)));
    if (Array.isArray(view.sections)) return view.sections.some((s) => scan(s.cards));
    return scan(view.cards);
  }

  _status(kind, msg) {
    const el = this.$("st");
    if (!el) return;
    el.className = "status " + (kind || "");
    el.textContent = msg;
  }

  _closeDialog() {
    const host = this.$("modalHost");
    if (host) host.innerHTML = "";
    this._activeCfg = null;
    this._renderDevices();
  }

  _esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
    );
  }
}

if (!customElements.get("multi-reef-panel")) {
  customElements.define("multi-reef-panel", MultiReefPanel);
}
console.info("%c MULTI-REEF-PANEL %c v0.5.1 ", "background:#3f8fd6;color:#fff", "color:#3f8fd6");
