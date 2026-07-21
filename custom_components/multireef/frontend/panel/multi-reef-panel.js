// Multi Reef — sidebar panel entry (<multi-reef-panel>).
//
// The integration's front door: hero header, tab bar, and lazily-created
// keep-alive views (Devices | Automations). Routing follows /multi-reef/<tab>
// via the HA-provided `route` property; tab clicks navigate() so the back
// button and deep links work. Served as an ES-module directory; cache-busted
// on the integration version by panel.py.

import { navigate } from "./util.js";
import { tokens, baseStyles } from "./styles.js";
import "./tabs.js";
import "./views/devices-view.js";
import "./views/automations-view.js";

const TABS = [
  { id: "devices", label: "Devices", icon: "mdi:fishbowl-outline" },
  { id: "automations", label: "Automations", icon: "mdi:robot-outline" },
];
const DEFAULT_TAB = "devices";
// Tab id -> element tag; views are created on first activation, then kept
// alive ([hidden]) so search/scroll state survives tab switches.
const VIEW_TAGS = {
  devices: "mr-devices-view",
  automations: "mr-automations-view",
};

class MultiReefPanel extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    // Forward to every instantiated view that accepts hass (setter on its class).
    for (const el of Object.values(this._views || {})) {
      if ("hass" in el) el.hass = hass;
    }
  }
  set narrow(v) {
    this.toggleAttribute("narrow", !!v);
    this._tabsEl?.toggleAttribute("narrow", !!v);
  }
  set route(v) {
    this._route = v;
    if (this._built) this._syncFromRoute();
  }
  set panel(v) {
    this._panelCfg = v;
    const version = v?.config?.version;
    if (version && !this._bannered) {
      this._bannered = true;
      console.info(
        `%c MULTI-REEF %c v${version} `,
        "background:#3f8fd6;color:#fff",
        "color:#3f8fd6"
      );
    }
  }

  _build() {
    this._built = true;
    this._views = {};
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}
        ${baseStyles}
        :host { display:block; height:100%; overflow-y:auto;
                background:var(--primary-background-color); color:var(--mr-text); }
        .wrap { max-width:1080px; margin:0 auto; padding:24px 20px 64px; }
        header.hero { display:flex; align-items:center; gap:14px; margin:8px 0 20px; }
        .logo { width:44px; height:44px; border-radius:12px; flex:0 0 auto;
                background:linear-gradient(135deg,var(--mr-blue),#2b6fb0);
                display:flex; align-items:center; justify-content:center; }
        .logo ha-icon { --mdc-icon-size:26px; color:#fff; }
        .hero h1 { margin:0; font-size:1.5rem; font-weight:600; letter-spacing:-.01em; }
        .hero p { margin:2px 0 0; color:var(--mr-muted); font-size:.9rem; }
        :host([narrow]) .hero p { display:none; }
        #viewhost { margin-top: 20px; }
        #viewhost > * { display:block; }
      </style>
      <div class="wrap">
        <header class="hero">
          <div class="logo"><ha-icon icon="mdi:fishbowl-outline"></ha-icon></div>
          <div>
            <h1>Multi Reef</h1>
            <p>Your reef devices — set up, organised, and on your dashboards.</p>
          </div>
        </header>
        <mr-tabs id="tabs"></mr-tabs>
        <div id="viewhost"></div>
      </div>`;

    this._tabsEl = this.shadowRoot.getElementById("tabs");
    this._tabsEl.tabs = TABS;
    this._tabsEl.addEventListener("tab-change", (e) => {
      if (e.detail.id !== this._activeTab) navigate(`/multi-reef/${e.detail.id}`);
    });
    this._syncFromRoute();
  }

  _syncFromRoute() {
    const seg = (this._route?.path || "").split("/").filter(Boolean)[0];
    const tab = TABS.some((t) => t.id === seg) ? seg : DEFAULT_TAB;
    this._activate(tab);
  }

  _activate(tab) {
    this._activeTab = tab;
    this._tabsEl.active = tab;
    const host = this.shadowRoot.getElementById("viewhost");
    if (!this._views[tab]) {
      const el = document.createElement(VIEW_TAGS[tab]);
      const version = this._panelCfg?.config?.version;
      if (version) el.setAttribute("data-version", version);
      this._views[tab] = el;
      host.appendChild(el);
      if (this._hass && "hass" in el) el.hass = this._hass;
    }
    for (const [id, el] of Object.entries(this._views)) {
      el.hidden = id !== tab;
    }
  }
}

if (!customElements.get("multi-reef-panel")) {
  customElements.define("multi-reef-panel", MultiReefPanel);
}
