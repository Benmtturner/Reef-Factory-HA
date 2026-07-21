// <mr-automations-view> — placeholder tab: establishes the panel's final shape
// (automations move in here later: reef-specific blueprints, dosing schedules,
// feed-mode scenes). Static content; no hass needed yet.

import { tokens, baseStyles, buttonStyles } from "../styles.js";
import { navigate } from "../util.js";

class MrAutomationsView extends HTMLElement {
  connectedCallback() {
    if (this.shadowRoot) return;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}
        ${baseStyles}
        ${buttonStyles}
        :host { display: block; }
        .coming { border: 1px dashed var(--mr-line); border-radius: var(--mr-radius);
                  padding: 48px 24px; text-align: center; color: var(--mr-muted); }
        .coming ha-icon { --mdc-icon-size: 40px; opacity: .6; }
        .coming h2 { margin: 14px 0 6px; font-size: 1.1rem; color: var(--mr-text); }
        .coming p { margin: 0 auto 18px; font-size: .9rem; max-width: 46ch; line-height: 1.5; }
      </style>
      <div class="coming">
        <ha-icon icon="mdi:robot-outline"></ha-icon>
        <h2>Automations are coming to Multi Reef</h2>
        <p>Reef-aware automations — dosing schedules, feed modes, alerts when a
           container runs low — will live here. For now, your devices' entities
           work with Home Assistant's automation editor.</p>
        <button class="btn ghost" id="open-ha">Open HA Automations</button>
      </div>`;
    this.shadowRoot.getElementById("open-ha").onclick = () => navigate("/config/automation/dashboard");
  }
}

if (!customElements.get("mr-automations-view")) {
  customElements.define("mr-automations-view", MrAutomationsView);
}
