// <mr-legacy-devices> — P1 transitional view: a verbatim behavior port of the
// original single-file panel body (anchor-keyword discovery, device card grid,
// bridges + firmware, supported chips). Replaced by the registry-driven
// devices-view in P2; only the provisioning dialog moved out (provision/).

import { esc } from "../util.js";
import { tokens, baseStyles, buttonStyles } from "../styles.js";
import "../provision/provision-dialog.js";

// The one brand-aware surface (P1 form — becomes catalog.js in P2).
const CATALOG = [
  {
    id: "rf-doser",
    brand: "Reef Factory",
    name: "Single-Head Doser",
    icon: "mdi:water-pump",
    anchorDomain: "sensor",
    anchorKeyword: "container_level",
    card: {
      type: "custom:reef-factory-doser-card",
      options: { grid_options: { columns: "full" } },
    },
  },
  {
    id: "redsea-dose",
    brand: "Red Sea",
    name: "ReefDose",
    icon: "mdi:water-plus",
    anchorDomain: "sensor",
    // "head_1_" is unique to ReefDose entities (the RF doser also has a
    // dosed_today sensor, so the head marker keeps the match unambiguous).
    anchorKeyword: "head_1_dosed_today",
    card: {
      type: "custom:reef-dose-card",
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
];

class MrLegacyDevices extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._renderDevices();
    this._renderBridges();
  }

  $(id) {
    return this.shadowRoot.getElementById(id);
  }

  // ---- device discovery (anchor-keyword scan — replaced by the store in P2) --
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
        const deviceId = reg?.device_id || entity_id;
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

  _build() {
    this._built = true;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}
        ${baseStyles}
        ${buttonStyles}
        :host { display: block; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:14px; }
        .dev { background:var(--mr-surface); border:1px solid var(--mr-line);
               border-radius:var(--mr-radius); padding:16px; display:flex; flex-direction:column; gap:12px;
               transition:border-color .15s ease; }
        .dev:hover { border-color:var(--mr-blue); }
        .dev .top { display:flex; align-items:center; gap:12px; }
        .dev .ic { width:40px; height:40px; border-radius:10px; flex:0 0 auto;
                   background:var(--mr-blue-dim);
                   display:flex; align-items:center; justify-content:center; }
        .dev .ic ha-icon { --mdc-icon-size:22px; color:var(--mr-blue); }
        .dev .name { font-weight:600; font-size:1rem; line-height:1.2; }
        .dev .brand { color:var(--mr-muted); font-size:.8rem; margin-top:1px; }
        .dev .anchor { color:var(--mr-muted); font-size:.74rem; font-family:monospace;
                       overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .empty { border:1px dashed var(--mr-line); border-radius:var(--mr-radius); padding:34px 20px;
                 text-align:center; color:var(--mr-muted); }
        .empty ha-icon { --mdc-icon-size:34px; color:var(--mr-muted); opacity:.6; }
        .empty p { margin:10px 0 0; font-size:.9rem; }
        .support { display:flex; flex-wrap:wrap; gap:8px; }
        .chip { display:inline-flex; align-items:center; gap:6px; font-size:.8rem;
                border:1px solid var(--mr-line); border-radius:999px; padding:5px 11px;
                color:var(--mr-muted); }
        .chip ha-icon { --mdc-icon-size:16px; }
      </style>
      <div class="sec-label" style="margin-top:0">Your devices</div>
      <div id="devices" class="grid"></div>

      <div class="sec-label" id="bridges-label" style="display:none">Bridges</div>
      <div id="bridges" class="grid"></div>

      <div class="sec-label">Supported devices</div>
      <div id="support" class="support"></div>
      <mr-provision-dialog id="prov"></mr-provision-dialog>
    `;
    this._renderSupport();
  }

  _renderSupport() {
    this.$("support").innerHTML = CATALOG.map(
      (c) => `<span class="chip"><ha-icon icon="${c.icon}"></ha-icon>${esc(c.brand)} · ${esc(c.name)}</span>`
    ).join("");
  }

  _renderDevices() {
    const host = this.$("devices");
    if (!host) return;
    const devices = this._discover();
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
              <div class="name">${esc(d.name)}</div>
              <div class="brand">${esc(d.entry.brand)} · ${esc(d.entry.name)}</div>
            </div>
          </div>
          <div class="anchor" title="${esc(d.anchorEntity)}">${esc(d.anchorEntity)}</div>
          <button class="btn" data-i="${i}">Add card to dashboard</button>
        </div>`
      )
      .join("");
    host.querySelectorAll("button[data-i]").forEach((b) => {
      b.onclick = () => {
        const d = this._devices[Number(b.dataset.i)];
        this.$("prov").open({
          hass: this._hass,
          title: d.entry.name,
          subtitle: d.name,
          cardMeta: d.entry.card,
          anchorEntity: d.anchorEntity,
          onDone: () => {
            this._devSig = null;
            this._renderDevices();
          },
        });
      };
    });
  }

  // ---- bridges: firmware over-the-air --------------------------------------
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
              <div class="name">${esc(b.name)}</div>
              <div class="brand">Firmware ${esc(b.installed || "?")}${
          b.updateAvailable ? " → " + esc(b.latest) : ""
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
}

if (!customElements.get("mr-legacy-devices")) {
  customElements.define("mr-legacy-devices", MrLegacyDevices);
}
