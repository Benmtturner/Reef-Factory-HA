// <mr-devices-view> — the registry-driven device directory (the scale answer).
//
// Toolbar (search + Add device) → Brand → Model collapsible groups → compact
// device rows (status dot · name · area chip · actions: add-card, rename,
// set-area, open-in-HA) → bridges section → About footer. Tree re-renders only
// on registry changes; status dots patch in place on state changes.
//
// Property: `hass`. Owns a MultiReefStore.

import { esc, debounce, navigate, loadJSON, saveJSON } from "../util.js";
import { tokens, baseStyles, buttonStyles } from "../styles.js";
import { MultiReefStore } from "../store.js";
import { addableBrands } from "../catalog.js";
import "./bridges-section.js";
import "../provision/provision-dialog.js";
import "../wizard/wizard.js";

const COLLAPSE_KEY = "multireef.panel.collapse";
const AUTOCOLLAPSE_OVER = 30;

class MrDevicesView extends HTMLElement {
  constructor() {
    super();
    this._store = new MultiReefStore();
    this._collapse = new Set(loadJSON(COLLAPSE_KEY, []));
    this._query = "";
    this._onSearch = debounce((v) => {
      this._query = v.trim().toLowerCase();
      this._renderTree();
    }, 150);
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) this._build();
    this._store.hass = hass;
    if (!this._store.ready && !this._inited) {
      this._inited = true;
      this._store.init(hass);
    }
  }

  $(id) {
    return this.shadowRoot.getElementById(id);
  }

  _build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}${baseStyles}${buttonStyles}
        :host { display:block; }
        .toolbar { display:flex; gap:10px; align-items:center; margin:0 0 8px; }
        .search { flex:1; display:flex; align-items:center; gap:8px; background:var(--mr-surface);
                  border:1px solid var(--mr-line); border-radius:10px; padding:0 12px; }
        .search ha-icon { --mdc-icon-size:20px; color:var(--mr-muted); }
        .search input { flex:1; border:none; background:none; outline:none; font-family:inherit;
                        font-size:.95rem; color:var(--mr-text); padding:11px 0; }
        .btn.add ha-icon { --mdc-icon-size:18px; margin-right:6px; vertical-align:-4px; }
        .count { color:var(--mr-muted); font-size:.8rem; margin:0 4px 12px; }
        .group { border:1px solid var(--mr-line); border-radius:var(--mr-radius); margin-bottom:12px;
                 overflow:hidden; background:var(--mr-surface); }
        .ghead { display:flex; align-items:center; gap:10px; padding:12px 14px; cursor:pointer;
                 user-select:none; }
        .ghead:hover { background:color-mix(in srgb, var(--mr-text) 4%, transparent); }
        .ghead .gic { width:30px; height:30px; border-radius:8px; flex:0 0 auto; background:var(--mr-blue-dim);
                      display:flex; align-items:center; justify-content:center; }
        .ghead .gic ha-icon { --mdc-icon-size:18px; color:var(--mr-blue); }
        .ghead .glabel { font-weight:600; font-size:1rem; flex:1; }
        .badge { font-size:.75rem; font-weight:600; color:var(--mr-muted); background:var(--primary-background-color);
                 border-radius:999px; padding:2px 9px; }
        .chev { --mdc-icon-size:20px; color:var(--mr-muted); transition:transform .15s ease; }
        .group.collapsed .chev { transform:rotate(-90deg); }
        .group.collapsed .gbody { display:none; }
        .gbtn { background:none; border:none; color:var(--mr-blue); font:inherit; font-size:.82rem;
                font-weight:600; cursor:pointer; padding:4px 6px; }
        .model-sub { padding:8px 14px 2px; font-size:.72rem; font-weight:600; text-transform:uppercase;
                     letter-spacing:.05em; color:var(--mr-muted); }
        .row { display:flex; align-items:center; gap:12px; padding:10px 14px;
               border-top:1px solid color-mix(in srgb, var(--mr-line) 60%, transparent); }
        .dot { width:9px; height:9px; border-radius:50%; flex:0 0 auto; background:var(--mr-muted); }
        .dot.ok { background:var(--mr-ok); }
        .dot.unavailable { background:var(--mr-err); }
        .rname { flex:1; min-width:0; font-weight:500; overflow:hidden; text-overflow:ellipsis;
                 white-space:nowrap; }
        .area { font-size:.76rem; color:var(--mr-muted); border:1px solid var(--mr-line); border-radius:999px;
                padding:3px 9px; cursor:pointer; white-space:nowrap; }
        .area:hover { border-color:var(--mr-blue); color:var(--mr-blue); }
        .acts { display:flex; gap:2px; flex:0 0 auto; }
        .iconbtn { background:none; border:none; cursor:pointer; color:var(--mr-muted); padding:6px;
                   border-radius:8px; display:inline-flex; }
        .iconbtn:hover { color:var(--mr-blue); background:var(--mr-blue-dim); }
        .iconbtn ha-icon { --mdc-icon-size:19px; }
        .iconbtn.addcard { color:var(--mr-blue); }
        .rename-in, .area-in { border:1px solid var(--mr-blue); border-radius:6px; padding:6px 8px;
                 font:inherit; font-size:.9rem; background:var(--primary-background-color); color:var(--mr-text); }
        .empty { border:1px dashed var(--mr-line); border-radius:var(--mr-radius); padding:40px 24px;
                 text-align:center; color:var(--mr-muted); }
        .empty ha-icon { --mdc-icon-size:36px; opacity:.6; }
        .empty h3 { margin:12px 0 6px; color:var(--mr-text); font-size:1.05rem; }
        .empty p { margin:0 auto 18px; max-width:44ch; font-size:.9rem; line-height:1.5; }
        .foot { margin-top:26px; padding-top:16px; border-top:1px solid var(--mr-line);
                color:var(--mr-muted); font-size:.78rem; display:flex; gap:14px; align-items:center; }
        .foot a { color:var(--mr-muted); }
        :host([narrow]) .row { flex-wrap:wrap; }
        :host([narrow]) .area { order:3; }
      </style>
      <div class="toolbar">
        <div class="search">
          <ha-icon icon="mdi:magnify"></ha-icon>
          <input id="search" type="text" placeholder="Search devices, models, areas…" autocomplete="off">
        </div>
        <button class="btn add" id="add-global"><ha-icon icon="mdi:plus"></ha-icon>Add device</button>
      </div>
      <div class="count" id="count"></div>
      <div id="tree"></div>
      <mr-bridges-section id="bridges"></mr-bridges-section>
      <div class="foot" id="foot"></div>
      <mr-provision-dialog id="prov"></mr-provision-dialog>
      <mr-wizard id="wizard"></mr-wizard>
    `;

    this.$("search").addEventListener("input", (e) => this._onSearch(e.target.value));
    this.$("add-global").onclick = () => this._openWizard();
    this.$("bridges").store = this._store;

    this._store.addEventListener("tree-changed", () => this._renderTree());
    this._store.addEventListener("status-changed", (e) => this._patchStatus(e.detail.deviceIds));
    this._store.addEventListener("error", () => this._renderError());
    // Delegated interactions on the tree.
    this.$("tree").addEventListener("click", (e) => this._onTreeClick(e));
    if (this._store.ready) this._renderTree();
  }

  // ---- render tree ---------------------------------------------------------

  _matches(dv, brandLabel) {
    if (!this._query) return true;
    const q = this._query;
    return (
      dv.name.toLowerCase().includes(q) ||
      (dv.model || "").toLowerCase().includes(q) ||
      (dv.areaName || "").toLowerCase().includes(q) ||
      (brandLabel || "").toLowerCase().includes(q)
    );
  }

  _renderTree() {
    if (!this.shadowRoot) return;
    const tree = this._store.tree;
    const host = this.$("tree");
    const total = this._store.counts.devices;
    const searching = !!this._query;

    if (!total) {
      this.$("count").textContent = "";
      host.innerHTML = `
        <div class="empty">
          <ha-icon icon="mdi:fishbowl-outline"></ha-icon>
          <h3>No devices yet</h3>
          <p>Add your reef gear — dosers, pumps, controllers — and it appears here,
             grouped by brand and model.</p>
          <button class="btn" id="add-empty"><ha-icon icon="mdi:plus"></ha-icon> Add your first device</button>
        </div>`;
      host.querySelector("#add-empty").onclick = () => this._openWizard();
      this._renderFooter();
      return;
    }

    let shown = 0;
    const html = tree
      .map((g) => {
        // filter models/devices by query
        const models = g.models
          .map((m) => ({ ...m, devices: m.devices.filter((d) => this._matches(d, g.brand.label)) }))
          .filter((m) => m.devices.length);
        const gShown = models.reduce((n, m) => n + m.devices.length, 0);
        if (searching && !gShown && !g.brand.label.toLowerCase().includes(this._query)) return "";
        shown += gShown;
        const collapsed = this._isCollapsed(g.brand.id, total) && !searching;
        const multiModel = g.models.length > 1;
        return `
        <div class="group ${collapsed ? "collapsed" : ""}" data-g="${esc(g.brand.id)}">
          <div class="ghead" data-toggle="${esc(g.brand.id)}">
            <div class="gic"><ha-icon icon="${esc(g.brand.icon)}"></ha-icon></div>
            <div class="glabel">${esc(g.brand.label)}</div>
            <span class="badge">${searching ? gShown + " / " + g.count : g.count}</span>
            ${addableBrands().some((b) => b.id === g.brand.id) ? `<button class="gbtn" data-addbrand="${esc(g.brand.id)}">Add</button>` : ""}
            <ha-icon class="chev" icon="mdi:chevron-down"></ha-icon>
          </div>
          <div class="gbody">
            ${models
              .map(
                (m) => `
              ${multiModel ? `<div class="model-sub">${esc(m.model)} · ${m.devices.length}</div>` : ""}
              ${m.devices.map((d) => this._rowHtml(d)).join("")}`
              )
              .join("")}
          </div>
        </div>`;
      })
      .join("");

    host.innerHTML = html || `<div class="count">No devices match “${esc(this._query)}”.</div>`;
    this.$("count").textContent = searching
      ? `${shown} of ${total} devices`
      : `${total} device${total === 1 ? "" : "s"}`;
    this._renderFooter();
  }

  _rowHtml(d) {
    const canCard = !!(d.cardMeta && this._store.anchorEntityFor(d));
    return `
      <div class="row" data-did="${esc(d.id)}">
        <span class="dot ${d.status || ""}"></span>
        <span class="rname" title="${esc(d.name)}">${esc(d.name)}</span>
        <span class="area" data-area="${esc(d.id)}">${d.areaName ? esc(d.areaName) : "Set area"}</span>
        <span class="acts">
          ${canCard ? `<button class="iconbtn addcard" data-addcard="${esc(d.id)}" title="Add card to dashboard"><ha-icon icon="mdi:view-dashboard-outline"></ha-icon></button>` : ""}
          <button class="iconbtn" data-rename="${esc(d.id)}" title="Rename"><ha-icon icon="mdi:pencil-outline"></ha-icon></button>
          <button class="iconbtn" data-open="${esc(d.id)}" title="Open in Home Assistant"><ha-icon icon="mdi:open-in-new"></ha-icon></button>
        </span>
      </div>`;
  }

  _renderFooter() {
    const v = this.getAttribute("data-version") || "";
    this.$("foot").innerHTML = `
      <span>Multi Reef${v ? " v" + esc(v) : ""}</span>
      <a href="https://github.com/Benmtturner/Reef-Factory-HA" target="_blank" rel="noopener">GitHub</a>`;
  }

  _renderError() {
    if (this._store.ready) return;
    this.$("tree").innerHTML = `<div class="empty"><ha-icon icon="mdi:alert-circle-outline"></ha-icon>
      <h3>Couldn't load your devices</h3><p>Retrying… if this persists, reload the page.</p></div>`;
  }

  // ---- status patch (no tree re-render) ------------------------------------

  _patchStatus(ids) {
    for (const id of ids) {
      const dv = this._store.deviceById(id);
      const dot = this.shadowRoot.querySelector(`.row[data-did="${cssEsc(id)}"] .dot`);
      if (dv && dot) dot.className = "dot " + (dv.status || "");
    }
  }

  // ---- collapse state ------------------------------------------------------

  // Overrides stored in _collapse: "<gid>" = explicitly collapsed,
  // "!<gid>" = explicitly expanded; absent = default (auto-collapse large fleets).
  _isCollapsed(gid, total) {
    if (this._collapse.has("!" + gid)) return false;
    if (this._collapse.has(gid)) return true;
    return total > AUTOCOLLAPSE_OVER;
  }
  _toggleCollapse(gid, total) {
    const nowCollapsed = this._isCollapsed(gid, total);
    this._collapse.delete(gid);
    this._collapse.delete("!" + gid);
    this._collapse.add(nowCollapsed ? "!" + gid : gid); // set the opposite as an explicit override
    saveJSON(COLLAPSE_KEY, [...this._collapse]);
    this._renderTree();
  }

  // ---- interactions --------------------------------------------------------

  _onTreeClick(e) {
    const t = (sel) => e.target.closest(`[${sel}]`);
    let el;
    if ((el = t("data-toggle"))) return this._toggleCollapse(el.dataset.toggle, this._store.counts.devices);
    if ((el = t("data-addbrand"))) {
      e.stopPropagation();
      const brand = addableBrands().find((b) => b.id === el.dataset.addbrand);
      return this._openWizard(brand?.flowStep);
    }
    if ((el = t("data-addcard"))) return this._addCard(el.dataset.addcard);
    if ((el = t("data-rename"))) return this._startRename(el.dataset.rename);
    if ((el = t("data-open"))) return navigate("/config/devices/device/" + el.dataset.open);
    if ((el = t("data-area"))) return this._startArea(el.dataset.area);
  }

  _addCard(id) {
    const d = this._store.deviceById(id);
    const anchor = this._store.anchorEntityFor(d);
    if (!d || !anchor) return;
    this.$("prov").open({
      hass: this._hass,
      title: d.model || d.name,
      subtitle: d.name,
      cardMeta: { type: d.cardMeta.type, options: d.cardMeta.options, variants: d.cardMeta.variants },
      anchorEntity: anchor,
      onDone: () => {},
    });
  }

  _startRename(id) {
    const row = this.shadowRoot.querySelector(`.row[data-did="${cssEsc(id)}"]`);
    const d = this._store.deviceById(id);
    if (!row || !d) return;
    const nameEl = row.querySelector(".rname");
    const input = document.createElement("input");
    input.className = "rename-in rname";
    input.value = d.name;
    nameEl.replaceWith(input);
    input.focus();
    input.select();
    const commit = async (save) => {
      if (input._done) return;
      input._done = true;
      if (save && input.value.trim() && input.value.trim() !== d.name) {
        try {
          await this._store.rename(id, input.value.trim());
        } catch (_) {}
      }
      this._renderTree(); // simplest correct refresh
    };
    input.onblur = () => commit(true);
    input.onkeydown = (ev) => {
      if (ev.key === "Enter") commit(true);
      else if (ev.key === "Escape") commit(false);
    };
  }

  _startArea(id) {
    const row = this.shadowRoot.querySelector(`.row[data-did="${cssEsc(id)}"]`);
    const d = this._store.deviceById(id);
    if (!row || !d) return;
    const chip = row.querySelector(".area");
    const sel = document.createElement("select");
    sel.className = "area-in area";
    const areas = this._store.areas;
    sel.innerHTML =
      `<option value="">— No area —</option>` +
      areas.map((a) => `<option value="${esc(a.area_id)}" ${a.area_id === d.areaId ? "selected" : ""}>${esc(a.name)}</option>`).join("") +
      `<option value="__new__">+ New area…</option>`;
    chip.replaceWith(sel);
    sel.focus();
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      this._renderTree();
    };
    sel.onchange = async () => {
      const v = sel.value;
      try {
        if (v === "__new__") {
          const name = window.prompt("New area name");
          if (name && name.trim()) {
            const areaId = await this._store.createArea(name.trim());
            await this._store.setArea(id, areaId);
          }
        } else {
          await this._store.setArea(id, v || null);
        }
      } catch (_) {}
      finish();
    };
    sel.onblur = finish;
  }

  _openWizard(menuChoice) {
    const wiz = this.$("wizard");
    if (wiz && wiz.open) return wiz.open({ store: this._store, menuChoice });
    navigate("/config/integrations/dashboard/add?domain=multireef");
  }
}

// CSS.escape shim for querySelector on registry ids (safe subset).
function cssEsc(s) {
  return String(s).replace(/["\\\]#.:>~+*\s]/g, "\\$&");
}

if (!customElements.get("mr-devices-view")) {
  customElements.define("mr-devices-view", MrDevicesView);
}
