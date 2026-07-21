// <mr-provision-dialog> — the add-card-to-dashboard dialog, ported verbatim in
// behavior from the original panel (dashboard → view pickers, variant selects,
// strategy-dashboard warning, duplicate guard, lovelace save, auto-close).
//
// open({ hass, title, subtitle, cardMeta, anchorEntity, onDone }) where
// cardMeta = { type, options, variants } (catalog `card` shape).

import { esc } from "../util.js";
import { tokens, baseStyles, buttonStyles, dialogStyles } from "../styles.js";
import { loadDashboards, loadViews, saveConfig, buildCard, appendCard, alreadyHas } from "./lovelace.js";

class MrProvisionDialog extends HTMLElement {
  $(id) {
    return this.shadowRoot && this.shadowRoot.getElementById(id);
  }

  async open({ hass, title, subtitle, cardMeta, anchorEntity, onDone }) {
    this._hass = hass;
    this._cardMeta = cardMeta;
    this._anchor = anchorEntity;
    this._onDone = onDone;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${tokens}${baseStyles}${buttonStyles}${dialogStyles}</style>
      <div class="modal" id="ov">
        <div class="dialog">
          <h3>Add ${esc(title)} card</h3>
          <p class="sub">${esc(subtitle)} → choose where it goes.</p>
          <label>Dashboard</label>
          <select id="dash"><option>Loading…</option></select>
          <label>View</label>
          <select id="view"><option>—</option></select>
          ${(cardMeta.variants || [])
            .map(
              (v) => `
          <label>${esc(v.label)}</label>
          <select id="var-${esc(v.key)}">${v.options
            .map(([val, text]) => `<option value="${esc(val)}">${esc(text)}</option>`)
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
      if (e.target.id === "ov") this.close();
    };
    this.$("cancel").onclick = () => this.close();

    const dashSel = this.$("dash");
    const viewSel = this.$("view");
    const addBtn = this.$("add");

    let dashboards = [];
    try {
      dashboards = await loadDashboards(hass);
    } catch (e) {
      this._status("err", "Couldn't load dashboards.");
      return;
    }
    dashSel.innerHTML = dashboards
      .map((d, i) => `<option value="${i}">${esc(d.title)}</option>`)
      .join("");

    const refreshViews = async () => {
      viewSel.innerHTML = `<option>Loading…</option>`;
      addBtn.disabled = true;
      this._status("", "");
      const dash = dashboards[Number(dashSel.value)];
      try {
        const cfg = await loadViews(hass, dash.url_path);
        this._activeCfg = cfg;
        const views = cfg.views || [];
        if (cfg.strategy || !views.length) {
          viewSel.innerHTML = `<option>—</option>`;
          this._status("warn", "Auto-generated dashboard — open it and “Take control” first.");
          return;
        }
        viewSel.innerHTML = views
          .map((v, i) => `<option value="${i}">${esc(v.title || v.path || "View " + (i + 1))}</option>`)
          .join("");
        this._maybeEnable();
      } catch (e) {
        viewSel.innerHTML = `<option>—</option>`;
        this._status("err", "Couldn't read that dashboard (it may be in YAML mode).");
      }
    };

    dashSel.onchange = refreshViews;
    viewSel.onchange = () => this._maybeEnable();
    addBtn.onclick = () => this._provision(dashboards[Number(dashSel.value)]);
    await refreshViews();
  }

  _maybeEnable() {
    const viewSel = this.$("view");
    const addBtn = this.$("add");
    const view = this._activeCfg?.views?.[Number(viewSel.value)];
    if (!view || (!Array.isArray(view.sections) && !Array.isArray(view.cards))) {
      addBtn.disabled = true;
      return;
    }
    if (alreadyHas(view, this._cardMeta.type, this._anchor)) {
      addBtn.disabled = true;
      this._status("warn", "This device's card is already on that view.");
    } else {
      addBtn.disabled = false;
      this._status("", "");
    }
  }

  async _provision(dash) {
    const addBtn = this.$("add");
    addBtn.disabled = true;
    this._status("", "Adding…");
    const cfg = this._activeCfg;
    const view = cfg.views[Number(this.$("view").value)];
    const variantValues = {};
    for (const v of this._cardMeta.variants || []) {
      const sel = this.$(`var-${v.key}`);
      if (sel && sel.value) variantValues[v.key] = sel.value;
    }
    const card = buildCard(this._cardMeta, this._anchor, variantValues);
    if (!appendCard(view, card)) {
      this._status("err", "That view can't take a card (auto-generated layout).");
      return;
    }
    try {
      await saveConfig(this._hass, dash.url_path, cfg);
      const where = dash.title + " → " + (view.title || view.path || "view");
      this._status("ok", "Added to " + where + ".");
      setTimeout(() => this.close(), 1100);
    } catch (e) {
      this._status("err", "Save failed: " + (e?.message || "unknown error"));
      addBtn.disabled = false;
    }
  }

  _status(kind, msg) {
    const el = this.$("st");
    if (!el) return;
    el.className = "status " + (kind || "");
    el.textContent = msg;
  }

  close() {
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
    this._activeCfg = null;
    if (this._onDone) this._onDone();
  }
}

if (!customElements.get("mr-provision-dialog")) {
  customElements.define("mr-provision-dialog", MrProvisionDialog);
}
