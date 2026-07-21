// <mr-bridges-section> — the bridge (hub) cards with one-click firmware OTA,
// pinned under the device directory. Reads BridgeView[] from the store; cards
// stay the metaphor here (few, action-rich). Hidden when there are no bridges.
//
// Property: `store` (MultiReefStore). Re-renders on tree-changed; firmware
// button state patched on status-changed.

import { esc } from "../util.js";
import { tokens, baseStyles, buttonStyles } from "../styles.js";

class MrBridgesSection extends HTMLElement {
  set store(store) {
    this._store = store;
    if (!this.shadowRoot) this._build();
    store.addEventListener("tree-changed", () => this._render());
    store.addEventListener("status-changed", () => this._render());
    if (store.ready) this._render();
  }

  _build() {
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}${baseStyles}${buttonStyles}
        :host { display: block; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }
        .dev { background:var(--mr-surface); border:1px solid var(--mr-line);
               border-radius:var(--mr-radius); padding:16px; display:flex; flex-direction:column; gap:12px; }
        .top { display:flex; align-items:center; gap:12px; }
        .ic { width:40px; height:40px; border-radius:10px; flex:0 0 auto; background:var(--mr-blue-dim);
              display:flex; align-items:center; justify-content:center; }
        .ic ha-icon { --mdc-icon-size:22px; color:var(--mr-blue); }
        .name { font-weight:600; font-size:1rem; line-height:1.2; }
        .sub { color:var(--mr-muted); font-size:.8rem; margin-top:1px; }
      </style>
      <div class="sec-label" id="label" hidden>Bridges</div>
      <div class="grid" id="grid"></div>`;
  }

  _render() {
    const bridges = this._store?.bridges || [];
    const label = this.shadowRoot.getElementById("label");
    const grid = this.shadowRoot.getElementById("grid");
    label.hidden = bridges.length === 0;
    if (!bridges.length) {
      grid.innerHTML = "";
      return;
    }
    grid.innerHTML = bridges
      .map((b, i) => {
        const btn = b.inProgress
          ? `<button class="btn" disabled>Updating…</button>`
          : b.updateAvailable
          ? `<button class="btn" data-b="${i}">Update firmware</button>`
          : `<button class="btn ghost" disabled>Up to date</button>`;
        const fw = `Firmware ${esc(b.installed || "?")}${b.updateAvailable ? " → " + esc(b.latest) : ""}`;
        const kids = b.childCount ? ` · ${b.childCount} device${b.childCount === 1 ? "" : "s"}` : "";
        return `
        <div class="dev">
          <div class="top">
            <div class="ic"><ha-icon icon="mdi:access-point"></ha-icon></div>
            <div style="min-width:0">
              <div class="name">${esc(b.device.name)}</div>
              <div class="sub">${fw}${kids}</div>
            </div>
          </div>
          ${btn}
        </div>`;
      })
      .join("");
    grid.querySelectorAll("button[data-b]").forEach((btn) => {
      btn.onclick = () => this._update(bridges[Number(btn.dataset.b)]);
    });
  }

  async _update(b) {
    if (!b || !b.updateAvailable || b.inProgress || !b.updateEntityId) return;
    try {
      await this._store.hass.callService("update", "install", { entity_id: b.updateEntityId });
    } catch (e) {
      /* HA surfaces the error toast */
    }
  }
}

if (!customElements.get("mr-bridges-section")) {
  customElements.define("mr-bridges-section", MrBridgesSection);
}
