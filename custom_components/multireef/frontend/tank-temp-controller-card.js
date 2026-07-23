/* Tank Temp Controller Card — D-D style aquarium temperature controller
 * Reads a temp sensor, shows heat/cool/alarm status, tap to set
 * setpoint / variance / alarm band / enable.
 * Config (all optional, defaults to the 3K tank entities):
 *   type: custom:tank-temp-controller-card
 *   name: 3K Tank
 *   temp_entity / heat_entity / cool_entity / alarm_entity /
 *   setpoint_entity / variance_entity / alarm_band_entity / enable_entity
 */
class TankTempControllerCard extends HTMLElement {
  static getStubConfig() { return { name: "3K Tank" }; }

  setConfig(config) {
    this._config = {
      name: "3K Tank",
      temp_entity: "sensor.rsato_4037531156_temperature",
      heat_entity: "switch.3k_heat",
      cool_entity: "switch.3k_cool",
      alarm_entity: "input_boolean.3k_tank_temp_alarm",
      setpoint_entity: "input_number.3k_tank_setpoint",
      variance_entity: "input_number.3k_tank_variance",
      alarm_band_entity: "input_number.3k_tank_alarm_band",
      cooling_range_entity: "input_number.3k_tank_cooling_range",
      enable_entity: "input_boolean.3k_tank_controller_enabled",
      ...config,
    };
    this._showSettings = false;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._update();
  }

  _st(id) {
    const s = this._hass && this._hass.states[id];
    return s ? s.state : "unavailable";
  }
  _num(id, dflt) {
    const v = parseFloat(this._st(id));
    return isNaN(v) ? dflt : v;
  }

  _render() {
    const c = this._config;
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .bezel {
          background: linear-gradient(160deg, #23272b 0%, #101214 70%);
          border-radius: 18px; padding: 14px 16px 12px;
          border: 1px solid rgba(255,255,255,0.07);
          box-shadow: 0 6px 18px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
          cursor: pointer; user-select: none; position: relative;
        }
        .brand {
          display: flex; justify-content: space-between; align-items: baseline;
          font: 600 11px/1 sans-serif; letter-spacing: 2px;
          color: #9aa4ae; text-transform: uppercase; margin: 0 2px 10px;
        }
        .brand .en { font-size: 10px; letter-spacing: 1px; }
        .en.off { color: #e05555; }
        .lcd {
          display: flex; align-items: stretch; gap: 10px;
          background: radial-gradient(120% 160% at 30% 20%, #2f7fe8 0%, #1b56c4 55%, #12409e 100%);
          border-radius: 10px; padding: 12px 16px;
          box-shadow: inset 0 3px 14px rgba(0,0,0,0.55), inset 0 -1px 6px rgba(255,255,255,0.15);
        }
        .icons { display: flex; flex-direction: column; justify-content: space-between; padding: 2px 0; }
        .ico { width: 24px; height: 24px; opacity: 0.28; color: #dbe9ff;
               filter: drop-shadow(0 0 1px rgba(0,0,0,0.4)); transition: opacity .2s, color .2s; }
        .ico.on-cool  { opacity: 1; color: #bfe6ff; filter: drop-shadow(0 0 6px #9fd4ff); }
        .ico.on-heat  { opacity: 1; color: #ffd9a8; filter: drop-shadow(0 0 6px #ffb35c); }
        .ico.on-alarm { opacity: 1; color: #ffb4b4; filter: drop-shadow(0 0 6px #ff6b6b);
                        animation: blink 0.9s step-end infinite; }
        @keyframes blink { 50% { opacity: 0.15; } }
        .readout { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }
        .digits {
          font: 700 58px/1 "Courier New", monospace; color: #f2f8ff;
          transform: skewX(-5deg); letter-spacing: 2px;
          text-shadow: 0 0 10px rgba(220,240,255,0.75), 0 2px 2px rgba(0,20,60,0.5);
          display: flex; align-items: flex-start;
        }
        .digits .unit { font-size: 20px; margin: 6px 0 0 6px; transform: none; }
        .setline {
          margin-top: 8px; font: 600 11px/1 sans-serif; letter-spacing: 1px;
          color: rgba(235,245,255,0.75);
        }
        .label {
          text-align: center; margin-top: 9px;
          font: 700 11px/1 sans-serif; letter-spacing: 3px; color: #7f8a94; text-transform: uppercase;
        }
        /* settings overlay */
        .panel {
          position: absolute; inset: 0; border-radius: 18px;
          background: rgba(12,14,16,0.96); backdrop-filter: blur(4px);
          display: flex; flex-direction: column; padding: 14px 18px; z-index: 2;
        }
        .panel h3 { margin: 0 0 10px; font: 600 13px/1 sans-serif; letter-spacing: 2px;
                    color: #cfd8e3; text-transform: uppercase; display:flex; justify-content:space-between; }
        .panel h3 .x { cursor: pointer; color: #8a95a1; }
        .row { display: flex; align-items: center; justify-content: space-between; margin: 7px 0; }
        .row .t { font: 500 13px/1 sans-serif; color: #aeb8c4; }
        .ctl { display: flex; align-items: center; gap: 10px; }
        .btn {
          width: 30px; height: 30px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.12);
          background: #1d2226; color: #e8eef4; font: 700 16px/28px sans-serif; text-align: center;
          cursor: pointer;
        }
        .btn:active { background: #2c343a; }
        .val { font: 700 15px/1 "Courier New", monospace; color: #f2f8ff; min-width: 54px; text-align: center; }
        .tog { width: 46px; height: 26px; border-radius: 13px; background: #333a40; position: relative; cursor: pointer; transition: background .2s; }
        .tog.on { background: #2e7d32; }
        .tog::after { content: ""; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px;
                      border-radius: 50%; background: #dfe6ec; transition: left .2s; }
        .tog.on::after { left: 23px; }
      </style>
      <ha-card>
        <div class="bezel" id="bezel">
          <div class="brand"><span>${c.name} · Temp Controller</span><span class="en" id="en-badge">ON</span></div>
          <div class="lcd">
            <div class="icons">
              <ha-icon class="ico" id="ico-cool" icon="mdi:snowflake"></ha-icon>
              <ha-icon class="ico" id="ico-heat" icon="mdi:fire"></ha-icon>
              <ha-icon class="ico" id="ico-alarm" icon="mdi:alarm-light"></ha-icon>
            </div>
            <div class="readout">
              <div class="digits"><span id="temp">--.-</span><span class="unit">°C</span></div>
              <div class="setline" id="setline">SET --.- · ±-.- · ALM ±-.-</div>
            </div>
          </div>
          <div class="label">Dual Heating &amp; Cooling Controller</div>
        </div>
      </ha-card>`;
    this.shadowRoot.getElementById("bezel").addEventListener("click", () => this._openSettings());
    this._update();
  }

  _update() {
    if (!this._hass || !this.shadowRoot || this._showSettings) return;
    const c = this._config;
    const t = this._num(c.temp_entity, null);
    const el = (id) => this.shadowRoot.getElementById(id);
    if (!el("temp")) return;
    el("temp").textContent = t === null ? "--.-" : t.toFixed(1);
    const sp = this._num(c.setpoint_entity, 25), va = this._num(c.variance_entity, 0.3),
          ab = this._num(c.alarm_band_entity, 1), cr = this._num(c.cooling_range_entity, 1);
    el("setline").textContent =
      `SET ${sp.toFixed(1)} · ±${va.toFixed(1)} · COOL +${cr.toFixed(1)} · ALM ±${ab.toFixed(1)}`;
    el("ico-cool").classList.toggle("on-cool", this._st(c.cool_entity) === "on");
    el("ico-heat").classList.toggle("on-heat", this._st(c.heat_entity) === "on");
    el("ico-alarm").classList.toggle("on-alarm", this._st(c.alarm_entity) === "on");
    const en = this._st(c.enable_entity) === "on";
    const badge = el("en-badge");
    badge.textContent = en ? "ON" : "STANDBY";
    badge.classList.toggle("off", !en);
  }

  _openSettings() {
    if (this._showSettings) return;
    this._showSettings = true;
    const c = this._config;
    const panel = document.createElement("div");
    panel.className = "panel";
    const rows = [
      ["Setpoint", c.setpoint_entity, 0.1, 18, 32],
      ["Variance ±", c.variance_entity, 0.1, 0.1, 3],
      ["Cooling range +", c.cooling_range_entity, 0.1, 0.3, 5],
      ["Alarm band ±", c.alarm_band_entity, 0.1, 0.2, 5],
    ];
    panel.innerHTML = `
      <h3><span>Controller settings</span><span class="x" id="close">✕</span></h3>
      ${rows.map(([label, ent], i) => `
        <div class="row"><span class="t">${label}</span>
          <span class="ctl">
            <span class="btn" data-i="${i}" data-d="-1">−</span>
            <span class="val" id="val-${i}">-</span>
            <span class="btn" data-i="${i}" data-d="1">+</span>
          </span></div>`).join("")}
      <div class="row"><span class="t">Controller enabled</span><span class="tog" id="tog"></span></div>`;
    this.shadowRoot.querySelector(".bezel").appendChild(panel);
    const refresh = () => {
      rows.forEach(([, ent], i) => {
        panel.querySelector(`#val-${i}`).textContent = this._num(ent, 0).toFixed(1);
      });
      panel.querySelector("#tog").classList.toggle("on", this._st(c.enable_entity) === "on");
    };
    refresh();
    panel.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const b = ev.target.closest(".btn");
      if (b) {
        const [label, ent, step, min, max] = rows[+b.dataset.i];
        const next = Math.min(max, Math.max(min, this._num(ent, min) + step * +b.dataset.d));
        this._hass.callService("input_number", "set_value",
          { entity_id: ent, value: Math.round(next * 10) / 10 });
        setTimeout(refresh, 300);
      }
      if (ev.target.id === "tog" ) {
        const on = this._st(c.enable_entity) === "on";
        this._hass.callService("input_boolean", on ? "turn_off" : "turn_on",
          { entity_id: c.enable_entity });
        setTimeout(refresh, 300);
      }
      if (ev.target.id === "close") {
        panel.remove();
        this._showSettings = false;
        this._update();
      }
    });
  }

  getCardSize() { return 3; }
}
if (!customElements.get("tank-temp-controller-card")) {
  customElements.define("tank-temp-controller-card", TankTempControllerCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "tank-temp-controller-card",
    name: "Tank Temp Controller Card",
    description: "D-D style aquarium heating/cooling controller display",
  });
}
