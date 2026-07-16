/*
 * Reef Factory Doser card — a Lovelace card for the RFDP single-head doser.
 *
 * The reef_factory_kh integration bundles and auto-loads this file (served at
 * /reef_factory_kh/reef-factory-doser-card.js), so no manual www/ copy or
 * Lovelace-resource step is needed — just add the card:
 *
 *   type: custom:reef-factory-doser-card
 *   entity: sensor.x1_dosser_container_level   # any entity of the doser device
 *   grid_options: { columns: full }            # give it full width in sections
 */

const NS = "http://www.w3.org/2000/svg";

// Map a logical role to how we find its entity on the device (domain + a
// case-insensitive substring of the entity_id, most-specific first).
const ROLES = {
  level:        ["sensor", "container_level"],
  reservoir:    ["sensor", "reservoir"],
  capacity:     ["sensor", "capacity"],
  todayTotal:   ["sensor", "dose_total"],
  dosedToday:   ["sensor", "dosed_today"],
  nextDose:     ["sensor", "next_dose"],
  timeLeft:     ["sensor", "time_left"],
  dosingDays:   ["sensor", "dosing_days"],
  nextCal:      ["sensor", "next_calibration"],
  lastDose:     ["sensor", "last_dose"],
  lastDoseTime: ["sensor", "last_dose_time"],
  numDoses:     ["sensor", "number_of_doses"],
  dosing:       ["binary_sensor", "dosing"],
  levelNum:     ["number", "reservoir_level"],
  capacityNum:  ["number", "container_capacity"],
  stopRefill:   ["button", "stop_refill"],
  fillCircuit:  ["button", "fill_circuit"],
  runCal:       ["button", "calibration"],
};

const fmt = (v, d = 2, unit = "") =>
  v == null || isNaN(v) ? "—" : `${Number(v).toFixed(d)}${unit}`;

// "H:MM"/"HH:MM" → "HH:MM" (for <input type=time>) and → minutes-of-day.
const hhmm = (t) => {
  const [h, m] = String(t == null ? "0:00" : t).split(":");
  return `${String(Number(h) || 0).padStart(2, "0")}:${String(Number(m) || 0).padStart(2, "0")}`;
};
const toMin = (t) => {
  const [h, m] = String(t == null ? "0:00" : t).split(":");
  return (Number(h) || 0) * 60 + (Number(m) || 0);
};

class ReefFactoryDoserCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("Set 'entity' to any entity of the doser device");
    this._config = config;
    this._built = false;
  }

  getCardSize() {
    return 8;
  }

  set hass(hass) {
    this._hass = hass;
    this._resolve();
    if (!this._built) this._build();
    this._update();
  }

  // --- entity resolution ---------------------------------------------------
  _resolve() {
    const hass = this._hass;
    const anchor = hass.entities?.[this._config.entity];
    this._deviceId = anchor?.device_id;
    const ids = this._deviceId
      ? Object.values(hass.entities).filter((e) => e.device_id === this._deviceId).map((e) => e.entity_id)
      : Object.keys(hass.states);
    this._e = {};
    for (const [role, [domain, needle]] of Object.entries(ROLES)) {
      this._e[role] = ids.find(
        (id) => id.startsWith(domain + ".") && id.toLowerCase().includes(needle)
      );
    }
    this._title =
      (this._deviceId && hass.devices?.[this._deviceId]?.name_by_user) ||
      hass.devices?.[this._deviceId]?.name ||
      "Doser";
  }

  _st(role) {
    const id = this._e[role];
    return id ? this._hass.states[id] : undefined;
  }
  _num(role) {
    const s = this._st(role);
    return s ? Number(s.state) : NaN;
  }

  // --- structure (built once) ---------------------------------------------
  _build() {
    this._built = true;
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { --rf-blue:#3f8fd6; }
        ha-card { padding:16px; box-sizing:border-box; overflow:hidden; }
        .grid { display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); grid-template-areas:"today beaker dosing" "refill beaker calibrate"; gap:14px 12px; align-items:start; }
        .grid > div { min-width:0; }
        @media (max-width:460px) {
          .grid { grid-template-columns:1fr 1fr; grid-template-areas:"today dosing" "beaker beaker" "refill calibrate"; }
          .beaker { margin:6px 0; }
        }
        .today { grid-area:today; }
        .dosing { grid-area:dosing; text-align:right; }
        .beaker { grid-area:beaker; display:flex; justify-content:center; }
        .refill { grid-area:refill; align-self:end; }
        .calibrate { grid-area:calibrate; align-self:end; text-align:right; }
        .label { color:var(--secondary-text-color); font-size:.75rem; letter-spacing:.06em; text-transform:uppercase; }
        .big { color:var(--rf-blue); font-size:2rem; line-height:1.05; font-weight:300; overflow-wrap:anywhere; }
        .big small { font-size:.95rem; font-weight:400; }
        .sub { color:var(--secondary-text-color); font-size:.82rem; margin-top:6px; line-height:1.4; overflow-wrap:anywhere; }
        .sub b { color:var(--primary-text-color); }
        .link { color:var(--rf-blue); cursor:pointer; font-weight:600; font-size:.82rem; }
        .link:hover { text-decoration:underline; }
        .btn { background:var(--rf-blue); color:#fff; border:none; border-radius:6px; padding:11px 16px; font-size:.9rem; cursor:pointer; transition:filter .15s ease, transform .1s ease; }
        .btn:hover { filter:brightness(1.1); } .btn:active { transform:translateY(1px); }
        .btn.red { background:var(--error-color,#e2574c); } .btn.wide { width:100%; }
        .sideL { text-align:right; color:var(--rf-blue); font-size:.85rem; line-height:1.4; align-self:center; }
        .sideL b { font-weight:700; }
        .warn { display:inline-block; background:var(--error-color,#e2574c); color:#fff; padding:3px 8px; border-radius:4px; font-size:.78rem; margin-bottom:4px; }
        .cal-date { color:var(--error-color,#e2574c); font-weight:700; }
        svg .grad { stroke:var(--rf-blue); stroke-width:1.5; }
        svg .cap { stroke:var(--rf-blue); stroke-width:7; }
        svg .fill { fill:var(--rf-blue); opacity:.4; transition:y .4s ease, height .4s ease; }
        svg .outline { fill:none; stroke:var(--rf-blue); stroke-width:2; }
        .beaker-wrap { display:flex; align-items:stretch; gap:6px; }
        .cap-lbl { fill:var(--rf-blue); font-size:14px; }
        /* dialog — themed */
        .modal { position:fixed; inset:0; background:rgba(0,0,0,.55); display:flex; align-items:center; justify-content:center; z-index:9; }
        .dialog { background:var(--ha-card-background,var(--card-background-color,#1f2226)); color:var(--primary-text-color); border-radius:10px; padding:22px; min-width:280px; max-width:min(92vw,420px); box-shadow:0 12px 44px rgba(0,0,0,.5); }
        .dialog h3 { margin:0 0 6px; text-align:center; }
        .dialog p { color:var(--secondary-text-color); text-align:center; margin:0 0 16px; font-size:.9rem; }
        .dialog label { display:block; font-size:.78rem; color:var(--secondary-text-color); margin:10px 0 4px; }
        .dialog input, .dialog select { width:100%; box-sizing:border-box; padding:10px; border:1px solid var(--divider-color,#555); border-radius:6px; font-size:1rem; background:var(--primary-background-color,#111); color:var(--primary-text-color); }
        .row { display:flex; gap:10px; margin-top:18px; } .row .btn { flex:1; }
        table { width:100%; border-collapse:collapse; font-size:.85rem; } th { color:var(--secondary-text-color); text-align:left; font-weight:600; }
        .days { display:flex; flex-wrap:wrap; gap:6px; }
        .days .day { border:1px solid var(--rf-blue); background:transparent; color:var(--rf-blue); border-radius:5px; padding:5px 9px; cursor:pointer; font-size:.82rem; }
        .days .day.on { background:var(--rf-blue); color:#fff; }
        hr { border:none; border-top:1px solid var(--divider-color,#444); margin:18px 0; }
        .dialog.wide { max-width:min(94vw,560px); }
        .btn.grn { background:var(--success-color,#43a047); }
        .btn.ghost { background:transparent; color:var(--rf-blue); border:1px solid var(--rf-blue); }
        .menu { display:flex; flex-direction:column; gap:8px; }
        .menu .btn { width:100%; }
        .sched-top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; font-size:.85rem; color:var(--secondary-text-color); }
        .sched-top b { color:var(--primary-text-color); }
        .sched-acts { display:flex; gap:6px; flex:0 0 auto; }
        .sched-acts .btn { padding:8px 10px; font-size:.78rem; }
        .adj { display:flex; gap:6px; align-items:center; margin:12px 0 4px; }
        .adj select, .adj input { flex:1; padding:8px; box-sizing:border-box; border:1px solid var(--divider-color,#555); border-radius:6px; background:var(--primary-background-color,#111); color:var(--primary-text-color); }
        .adj .btn { flex:0 0 auto; }
        .sched-head, .sched-row { display:grid; grid-template-columns:30px 1fr 1fr 52px 26px; gap:6px; align-items:center; }
        .sched-head { color:var(--secondary-text-color); font-size:.7rem; text-transform:uppercase; letter-spacing:.04em; padding:10px 2px 6px; }
        .sched-rows { max-height:46vh; overflow:auto; }
        .sched-row { padding:3px 0; }
        .sched-row input { width:100%; box-sizing:border-box; padding:7px 6px; border:1px solid var(--divider-color,#555); border-radius:6px; font-size:.9rem; background:var(--primary-background-color,#111); color:var(--primary-text-color); }
        .sched-row .rid { text-align:center; color:var(--secondary-text-color); font-size:.82rem; }
        .sched-row .rpct { text-align:right; color:var(--secondary-text-color); font-size:.8rem; }
        .sched-row .rdel { background:none; border:none; color:var(--error-color,#e2574c); cursor:pointer; font-size:1.05rem; line-height:1; padding:2px; }
        textarea { box-sizing:border-box; background:var(--primary-background-color,#111); color:var(--primary-text-color); border:1px solid var(--divider-color,#555); border-radius:6px; padding:8px; }
      </style>
      <ha-card>
        <div class="grid">
          <div class="today">
            <div class="label">Today</div>
            <div class="big"><span id="dosed">—</span> ml<small>/ <span id="target">—</span> ml</small></div>
            <div class="sub" id="lastaction"></div>
            <div class="link" id="showmore">Show more…</div>
          </div>
          <div class="dosing">
            <button class="btn" id="dosingBtn">DOSING</button>
            <div class="sub" id="nextdosing"></div>
          </div>
          <div class="beaker">
            <div class="beaker-wrap">
              <div class="sideL" id="sideL"></div>
              <svg id="svg" width="112" height="240" viewBox="0 0 112 240"></svg>
              <div style="display:flex;align-items:center;">
                <button class="btn" id="editBtn" style="padding:8px 14px;">EDIT</button>
              </div>
            </div>
          </div>
          <div class="refill"><button class="btn" id="refillBtn">MANUAL REFILL</button></div>
          <div class="calibrate">
            <div class="warn" id="calwarn" style="display:none;">Calibrate the device!</div>
            <div class="sub">Next calibration<br><span class="cal-date" id="caldate">—</span></div>
            <button class="btn" id="calBtn" style="margin-top:6px;">CALIBRATE</button>
          </div>
        </div>
        <div id="modalHost"></div>
      </ha-card>
    `;
    this._drawBeaker();
    const $ = (id) => root.getElementById(id);
    $("editBtn").onclick = () => this._dlgEdit();
    $("calBtn").onclick = () => this._dlgCalibrate();
    $("dosingBtn").onclick = () => this._dlgDosing();
    $("showmore").onclick = () => this._dlgHistory();
    this.$ = $;
  }

  _drawBeaker() {
    const svg = this.shadowRoot.getElementById("svg");
    svg.innerHTML = "";
    const x = 14, w = 84, top = 14, bot = 228;
    const line = (x1, y1, x2, y2, cls) => {
      const l = document.createElementNS(NS, "line");
      l.setAttribute("x1", x1); l.setAttribute("y1", y1);
      l.setAttribute("x2", x2); l.setAttribute("y2", y2);
      l.setAttribute("class", cls); svg.appendChild(l);
    };
    // fill rect (updated later)
    const fill = document.createElementNS(NS, "rect");
    fill.setAttribute("x", x); fill.setAttribute("width", w);
    fill.setAttribute("class", "fill"); fill.id = "fillrect";
    svg.appendChild(fill);
    // body outline (3 sides)
    const body = document.createElementNS(NS, "path");
    body.setAttribute("d", `M${x} ${top} L${x} ${bot} L${x + w} ${bot} L${x + w} ${top}`);
    body.setAttribute("class", "outline"); svg.appendChild(body);
    // top & bottom caps
    line(x, top, x + w, top, "cap");
    line(x - 3, bot, x + w + 3, bot, "cap");
    // graduations on the right
    for (let i = 1; i < 10; i++) {
      const y = top + (i * (bot - top)) / 10;
      line(x + w - (i % 2 ? 22 : 32), y, x + w, y, "grad");
    }
    const cap = document.createElementNS(NS, "text");
    cap.setAttribute("x", x + w - 4); cap.setAttribute("y", top + 18);
    cap.setAttribute("text-anchor", "end"); cap.setAttribute("class", "cap-lbl");
    cap.id = "caplbl"; svg.appendChild(cap);
    this._beaker = { top, bot };
  }

  // --- value update --------------------------------------------------------
  _update() {
    if (!this.$) return;
    const level = this._num("level");
    const cap = this._num("capacity");
    const pct = this._num("reservoir");
    this.$("dosed").textContent = fmt(this._num("dosedToday"), 2);
    // target = today total (+ manual daily portion if a refill is active — omitted v1)
    this.$("target").textContent = fmt(this._num("todayTotal"), 2);

    const la = this._st("lastDose");
    const lat = this._st("lastDoseTime");
    if (la && lat && lat.state !== "unknown") {
      const t = new Date(lat.state);
      this.$("lastaction").innerHTML =
        `Last action: ${t.toLocaleString()}<br>dosed <b>${fmt(la.state)} ml</b>.`;
    } else this.$("lastaction").textContent = "";

    const nd = this._st("nextDose");
    if (nd && nd.state !== "unknown") {
      const t = new Date(nd.state);
      const amt = nd.attributes?.amount_ml;
      this.$("nextdosing").innerHTML =
        `Next dose at <b>${t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</b>` +
        (amt != null ? `, amount: <b>${fmt(amt)} ml</b>.` : "");
    } else this.$("nextdosing").textContent = "";

    this.$("sideL").innerHTML =
      `Time left<br><b>${fmt(this._num("timeLeft"), 0)} days</b> ${fmt(pct, 0)}%<br>${fmt(level, 2)} ml`;

    // beaker fill
    const { top, bot } = this._beaker;
    const frac = isNaN(pct) ? 0 : Math.max(0, Math.min(1, pct / 100));
    const fr = this.shadowRoot.getElementById("fillrect");
    const h = (bot - top) * frac;
    fr.setAttribute("y", bot - h); fr.setAttribute("height", h);
    this.shadowRoot.getElementById("caplbl").textContent = fmt(cap, 2) + " ml";

    // calibration
    const calS = this._st("nextCal");
    if (calS && calS.state !== "unknown") {
      const cd = new Date(calS.state);
      this.$("caldate").textContent = cd.toLocaleDateString();
      const overdue = cd.getFullYear() < 2020 || cd < new Date();
      this.$("calwarn").style.display = overdue ? "inline-block" : "none";
    }

    // MANUAL REFILL ⇄ CANCEL MANUAL REFILL, driven by the active-refill flag
    const refillActive = this._st("dosing")?.attributes?.refill_active;
    const rb = this.$("refillBtn");
    if (refillActive) {
      rb.textContent = "CANCEL MANUAL REFILL";
      rb.classList.add("red");
      rb.onclick = () => this._e.stopRefill && this._call("button", "press", { entity_id: this._e.stopRefill });
    } else {
      rb.textContent = "MANUAL REFILL";
      rb.classList.remove("red");
      rb.onclick = () => this._dlgRefill();
    }
  }

  // --- dialogs -------------------------------------------------------------
  _modal(inner, cls = "") {
    const host = this.shadowRoot.getElementById("modalHost");
    host.innerHTML = `<div class="modal"><div class="dialog ${cls}">${inner}</div></div>`;
    host.querySelector(".modal").addEventListener("click", (e) => {
      if (e.target.classList.contains("modal")) host.innerHTML = "";
    });
    return host;
  }
  _close() { this.shadowRoot.getElementById("modalHost").innerHTML = ""; }

  _refillTarget() {
    // services are registered on the binary_sensor (dosing) entity
    return this._e.dosing;
  }
  _call(domain, service, data) {
    return this._hass.callService(domain, service, data);
  }

  _dlgRefill() {
    const host = this._modal(`
      <h3>Manual refill</h3><p>Specify how much liquid to add.</p>
      <label>Amount (ml)</label><input id="amt" type="number" min="0" step="0.1" />
      <label>Over how many days (0 = now)</label><input id="days" type="number" min="0" step="1" value="0" />
      <div class="row"><button class="btn" id="ok">OK</button><button class="btn red" id="cancel">CANCEL</button></div>
    `);
    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#ok").onclick = () => {
      const amount = parseFloat(host.querySelector("#amt").value);
      const days = parseInt(host.querySelector("#days").value || "0", 10);
      if (!isNaN(amount)) this._call("reef_factory_kh", "manual_refill", { entity_id: this._refillTarget(), amount, days });
      this._close();
    };
  }

  _dlgEdit() {
    const host = this._modal(`
      <h3>Edit container</h3>
      <label>Current contents (ml)</label><input id="cur" type="number" min="0" value="${this._num("level") || 0}" />
      <label>Capacity (ml)</label><input id="cap" type="number" min="1" value="${this._num("capacity") || 0}" />
      <div class="row"><button class="btn red" id="save">SAVE</button><button class="btn ghost" id="cancel">CANCEL</button></div>
    `);
    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#save").onclick = () => {
      const level = parseFloat(host.querySelector("#cur").value);
      const capacity = parseFloat(host.querySelector("#cap").value);
      // One combined write — two separate number sets race and cancel each other out.
      if (!isNaN(level) && !isNaN(capacity)) {
        this._call("reef_factory_kh", "set_container", { entity_id: this._refillTarget(), level, capacity });
      }
      this._close();
    };
  }

  // DOSING → menu (mirrors the app: edit / skip / export / import / history).
  _dlgDosing() {
    const host = this._modal(`
      <h3>Dosing</h3>
      <div class="menu">
        <button class="btn" id="edit">EDIT SCHEDULE</button>
        <button class="btn" id="skip">SKIP NEXT DOSE</button>
        <button class="btn ghost" id="export">EXPORT</button>
        <button class="btn ghost" id="import">IMPORT</button>
        <button class="btn ghost" id="history">HISTORY</button>
      </div>
      <div class="row"><button class="btn ghost" id="cancel">CANCEL</button></div>
    `);
    host.querySelector("#edit").onclick = () => this._dlgSchedule();
    host.querySelector("#skip").onclick = () => this._dlgSkip();
    host.querySelector("#export").onclick = () => this._dlgExport();
    host.querySelector("#import").onclick = () => this._dlgImport();
    host.querySelector("#history").onclick = () => this._dlgHistory();
    host.querySelector("#cancel").onclick = () => this._close();
  }

  // Per-dose grid: ID / Time / Value / Percent / ✕, with Add + Adjust + days.
  _dlgSchedule() {
    const src = this._st("nextDose")?.attributes?.schedule || [];
    let rows = src.map((s) => ({ time: hhmm(s.time), ml: Number(s.ml) || 0 }));
    if (!rows.length) rows = [{ time: "00:00", ml: 1 }];
    const active = new Set((this._st("dosingDays")?.state || "").split(",").map((d) => d.trim()).filter(Boolean));
    const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const host = this._modal(`
      <h3>Dosing schedule</h3>
      <div class="sched-top">
        <div>Liquid amount <b id="total">—</b> ml<br>Number of doses <b id="count">—</b></div>
        <div class="sched-acts">
          <button class="btn grn" id="adjust">ADJUST</button>
          <button class="btn grn" id="add">ADD A DOSE</button>
        </div>
      </div>
      <div id="adjbar"></div>
      <div class="days" id="days">${DAYS.map((d) => `<button type="button" class="day${active.has(d) ? " on" : ""}" data-d="${d}">${d}</button>`).join("")}</div>
      <div class="sched-head"><span>ID</span><span>Time</span><span>Value</span><span>%</span><span></span></div>
      <div id="rows" class="sched-rows"></div>
      <div class="row"><button class="btn" id="save">SAVE</button><button class="btn ghost" id="cancel">CANCEL</button></div>
    `, "wide");

    const sel = new Set(active);
    host.querySelectorAll(".day").forEach((b) => {
      b.onclick = () => {
        const d = b.dataset.d;
        if (sel.has(d)) { sel.delete(d); b.classList.remove("on"); }
        else { sel.add(d); b.classList.add("on"); }
      };
    });

    const refreshTotals = () => {
      const total = rows.reduce((a, r) => a + (Number(r.ml) || 0), 0);
      host.querySelector("#total").textContent = total.toFixed(2);
      host.querySelector("#count").textContent = String(rows.length);
      host.querySelectorAll(".rpct").forEach((el, i) => {
        const ml = Number(rows[i] ? rows[i].ml : 0) || 0;
        el.textContent = (total ? (ml / total) * 100 : 0).toFixed(2) + "%";
      });
    };
    const renderRows = () => {
      const rowsEl = host.querySelector("#rows");
      rowsEl.innerHTML = rows
        .map(
          (r, i) => `
        <div class="sched-row">
          <span class="rid">${i + 1}</span>
          <input class="rtime" data-i="${i}" type="time" value="${hhmm(r.time)}" />
          <input class="rml" data-i="${i}" type="number" min="0" step="0.01" value="${r.ml}" />
          <span class="rpct">0%</span>
          <button class="rdel" data-i="${i}" title="Remove">✕</button>
        </div>`
        )
        .join("");
      rowsEl.querySelectorAll(".rtime").forEach((el) => {
        el.onchange = () => { rows[+el.dataset.i].time = el.value || "00:00"; };
      });
      rowsEl.querySelectorAll(".rml").forEach((el) => {
        el.onchange = () => { rows[+el.dataset.i].ml = parseFloat(el.value) || 0; refreshTotals(); };
      });
      rowsEl.querySelectorAll(".rdel").forEach((el) => {
        el.onclick = () => {
          rows.splice(+el.dataset.i, 1);
          if (!rows.length) rows.push({ time: "00:00", ml: 1 });
          renderRows();
        };
      });
      refreshTotals();
    };

    host.querySelector("#add").onclick = () => {
      const used = new Set(rows.map((r) => hhmm(r.time)));
      let t = "12:00";
      for (let h = 0; h < 24; h++) {
        const c = `${String(h).padStart(2, "0")}:00`;
        if (!used.has(c)) { t = c; break; }
      }
      const avg = rows.length ? rows.reduce((a, r) => a + r.ml, 0) / rows.length : 1;
      rows.push({ time: t, ml: Math.round((avg || 1) * 100) / 100 });
      rows.sort((a, b) => toMin(a.time) - toMin(b.time));
      renderRows();
    };

    const adjbar = host.querySelector("#adjbar");
    host.querySelector("#adjust").onclick = () => {
      if (adjbar.innerHTML) { adjbar.innerHTML = ""; return; }
      adjbar.innerHTML = `
        <div class="adj">
          <select id="adjmode"><option value="pct">Adjust by %</option><option value="val">Set total (ml)</option></select>
          <input id="adjval" type="number" step="0.1" value="100" />
          <button class="btn red" id="adjupd">UPDATE</button>
        </div>`;
      const modeEl = adjbar.querySelector("#adjmode");
      const valEl = adjbar.querySelector("#adjval");
      modeEl.onchange = () => {
        valEl.value = modeEl.value === "pct" ? "100" : rows.reduce((a, r) => a + r.ml, 0).toFixed(2);
      };
      adjbar.querySelector("#adjupd").onclick = () => {
        const v = parseFloat(valEl.value);
        if (isNaN(v)) return;
        const total = rows.reduce((a, r) => a + r.ml, 0);
        const factor = modeEl.value === "pct" ? v / 100 : total ? v / total : 0;
        rows = rows.map((r) => ({ time: r.time, ml: Math.round(r.ml * factor * 100) / 100 }));
        renderRows();
      };
    };

    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#save").onclick = () => {
      const doses = rows
        .map((r) => ({ time: hhmm(r.time), ml: Number(r.ml) || 0 }))
        .filter((r) => r.ml > 0)
        .sort((a, b) => toMin(a.time) - toMin(b.time));
      if (doses.length) {
        const data = { entity_id: this._refillTarget(), doses };
        if (sel.size) data.days = [...sel];
        this._call("reef_factory_kh", "set_doses", data);
      }
      this._close();
    };

    renderRows();
  }

  _dlgSkip() {
    const host = this._modal(`
      <h3>Skip next dose</h3><p>How much of the next dose to skip (%).</p>
      <input id="pct" type="number" min="0" max="100" value="100" />
      <div class="row"><button class="btn red" id="ok">OK</button><button class="btn ghost" id="cancel">CANCEL</button></div>
    `);
    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#ok").onclick = () => {
      const percent = parseInt(host.querySelector("#pct").value, 10);
      if (!isNaN(percent)) this._call("reef_factory_kh", "skip_next", { entity_id: this._refillTarget(), percent });
      this._close();
    };
  }

  _dlgExport() {
    const doses = (this._st("nextDose")?.attributes?.schedule || []).map((s) => ({ time: hhmm(s.time), ml: Number(s.ml) || 0 }));
    const days = this._st("dosingDays")?.state || "";
    const json = JSON.stringify({ days, doses }, null, 2);
    const host = this._modal(`
      <h3>Export schedule</h3><p>Copy this to back up or share the schedule.</p>
      <textarea id="json" readonly style="width:100%;height:220px;">${json}</textarea>
      <div class="row"><button class="btn" id="copy">COPY</button><button class="btn ghost" id="cancel">CLOSE</button></div>
    `, "wide");
    host.querySelector("#copy").onclick = () => {
      const ta = host.querySelector("#json");
      ta.select();
      try { navigator.clipboard.writeText(ta.value); } catch (_) { document.execCommand("copy"); }
    };
    host.querySelector("#cancel").onclick = () => this._close();
  }

  _dlgImport() {
    const host = this._modal(`
      <h3>Import schedule</h3><p>Paste an exported schedule to apply it.</p>
      <textarea id="json" placeholder='{"doses":[{"time":"08:00","ml":2.5}]}' style="width:100%;height:200px;"></textarea>
      <div class="sub" id="err" style="color:var(--error-color,#e2574c);"></div>
      <div class="row"><button class="btn red" id="apply">APPLY</button><button class="btn ghost" id="cancel">CANCEL</button></div>
    `, "wide");
    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#apply").onclick = () => {
      let obj;
      try { obj = JSON.parse(host.querySelector("#json").value); } catch (_) { host.querySelector("#err").textContent = "Invalid JSON."; return; }
      const doses = (obj.doses || [])
        .map((d) => ({ time: hhmm(d.time), ml: Number(d.ml) || 0 }))
        .filter((d) => d.ml > 0);
      if (!doses.length) { host.querySelector("#err").textContent = "No valid doses found."; return; }
      const data = { entity_id: this._refillTarget(), doses };
      if (obj.days) {
        const dd = String(obj.days).split(",").map((x) => x.trim()).filter(Boolean);
        if (dd.length) data.days = dd;
      }
      this._call("reef_factory_kh", "set_doses", data);
      this._close();
    };
  }

  _dlgCalibrate() {
    const host = this._modal(`
      <h3>Calibration</h3>
      <p>1. Fill the circuit. 2. Run the pump ~30 s into a measuring cup.
      3. Enter the measured volume.</p>
      <div class="row">
        <button class="btn" id="fill">FILL CIRCUIT</button>
        <button class="btn" id="run">RUN 30 s</button>
      </div>
      <label>Measured volume (ml)</label><input id="meas" type="number" min="0" step="0.01" />
      <div class="row"><button class="btn red" id="submit">SUBMIT</button><button class="btn" id="cancel">CLOSE</button></div>
    `);
    host.querySelector("#fill").onclick = () => this._e.fillCircuit && this._call("button", "press", { entity_id: this._e.fillCircuit });
    host.querySelector("#run").onclick = () => this._e.runCal && this._call("button", "press", { entity_id: this._e.runCal });
    host.querySelector("#cancel").onclick = () => this._close();
    host.querySelector("#submit").onclick = () => {
      const measured_ml = parseFloat(host.querySelector("#meas").value);
      if (!isNaN(measured_ml)) this._call("reef_factory_kh", "submit_calibration", { entity_id: this._refillTarget(), measured_ml });
      this._close();
    };
  }

  _dlgHistory() {
    const nd = this._st("dosedToday");
    const hist = nd?.attributes?.history || [];
    const rows = hist
      .map((h) => `<tr><td>${h.time ? new Date(h.time).toLocaleString() : "—"}</td><td style="text-align:right">${fmt(h.ml)} ml</td><td>${h.type}</td></tr>`)
      .join("");
    const host = this._modal(`
      <h3>Dose history</h3>
      <div style="max-height:320px;overflow:auto;"><table style="width:100%;border-collapse:collapse;font-size:.85rem;">
        <thead><tr style="color:var(--rf-grey)"><th style="text-align:left">Time</th><th style="text-align:right">Amount</th><th style="text-align:left">Type</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="3">No history</td></tr>'}</tbody>
      </table></div>
      <div class="row"><button class="btn" id="cancel">CLOSE</button></div>
    `);
    host.querySelector("#cancel").onclick = () => this._close();
  }
}

// Some setups load a scoped-custom-element-registry polyfill (bundled by other
// cards, e.g. universal-remote-card) that replaces window.customElements AFTER
// we run, orphaning our early definition. Re-assert it across load phases — a
// fresh subclass each time dodges "constructor already used" — so whichever
// registry HA ends up querying has the element.
const RF_TAG = "reef-factory-doser-card";
const rfDefine = () => {
  if (customElements.get(RF_TAG)) return;
  try {
    customElements.define(RF_TAG, class extends ReefFactoryDoserCard {});
  } catch (_) {
    /* already defined in this registry */
  }
};
rfDefine();
window.addEventListener("load", rfDefine);
setTimeout(rfDefine, 1500);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "reef-factory-doser-card",
  name: "Reef Factory Doser",
  description: "Control card for the Reef Factory single-head doser (RFDP).",
});
console.info("%c REEF-FACTORY-DOSER-CARD %c v0.10.3 ", "background:#3f8fd6;color:#fff", "color:#3f8fd6");
