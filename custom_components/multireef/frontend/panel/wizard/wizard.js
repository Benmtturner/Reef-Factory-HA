// <mr-wizard> — the in-panel add-device wizard. Drives our config flow via the
// REST client and renders each step generically on step.type (menu | form |
// progress | create_entry | abort). Labels come from HA localize with a bundled
// fallback. Scan steps (reef_factory/redsea run a network sweep in the POST)
// show a live "Scanning…" state; Cancel stays active and aborts the flow.
//
// open({ store, menuChoice }) — if menuChoice matches a first-step menu option
// it's auto-submitted (per-brand Add skips the menu).

import { esc, fireEvent } from "../util.js";
import { tokens, baseStyles, buttonStyles, dialogStyles } from "../styles.js";
import { createFlow, submitStep, abortFlow, normalizeSchema } from "./flow-client.js";
import { MENU, MENU_PRESENTATION, STEPS, ERRORS, ABORTS, SCAN_STEPS, humanize } from "./strings.js";

class MrWizard extends HTMLElement {
  async open({ store, menuChoice } = {}) {
    this._store = store;
    this._hass = store?.hass || this._hass;
    this._menuChoice = menuChoice;
    this._flowId = null;
    this._closed = false;
    this._finished = false;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!this._escHandler) {
      this._escHandler = (e) => {
        if (e.key === "Escape") this.close();
      };
    }
    window.addEventListener("keydown", this._escHandler);
    // Preload backend translations for nicer copy (best-effort).
    try {
      await this._hass.loadBackendTranslation?.("config", "multireef");
    } catch (_) {}
    this._renderPending("Starting…");
    try {
      const step = await createFlow(this._hass);
      this._flowId = step.flow_id;
      // Per-brand Add jumps straight past the menu (menu_options may be a list
      // or an object — _menuOptionIds handles both).
      if (menuChoice && step.type === "menu" && this._menuOptionIds(step).includes(menuChoice)) {
        return this._submit({ next_step_id: menuChoice }, SCAN_STEPS.has(menuChoice));
      }
      this._renderStep(step);
    } catch (err) {
      this._renderError(err);
    }
  }

  close() {
    this._closed = true;
    window.removeEventListener("keydown", this._escHandler);
    if (this._progressUnsub) {
      try {
        this._progressUnsub();
      } catch (_) {}
      this._progressUnsub = null;
    }
    if (this._flowId && !this._finished) {
      abortFlow(this._hass, this._flowId).catch(() => {});
    }
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
  }

  // ---- localization helpers ------------------------------------------------

  _t(key, fallback) {
    const s = this._hass?.localize?.(key);
    return s || fallback;
  }
  _menuOptionIds(step) {
    const m = step.menu_options;
    return Array.isArray(m) ? m : m ? Object.keys(m) : [];
  }
  _menuLabel(step, id) {
    const m = step.menu_options;
    const fromStep = !Array.isArray(m) && m ? m[id] : undefined;
    return (
      fromStep ||
      this._t(`component.multireef.config.step.user.menu_options.${id}`, null) ||
      MENU[id] ||
      humanize(id)
    );
  }
  _stepTitle(step) {
    return this._t(`component.multireef.config.step.${step.step_id}.title`, null) || STEPS[step.step_id]?.title || "Add device";
  }
  _stepDesc(step) {
    return this._t(`component.multireef.config.step.${step.step_id}.description`, null) || STEPS[step.step_id]?.description || "";
  }
  _fieldLabel(step, name) {
    return (
      this._t(`component.multireef.config.step.${step.step_id}.data.${name}`, null) ||
      STEPS[step.step_id]?.data?.[name] ||
      humanize(name)
    );
  }
  _errorText(code) {
    return this._t(`component.multireef.config.error.${code}`, null) || ERRORS[code] || humanize(code);
  }
  _abortText(reason) {
    return this._t(`component.multireef.config.abort.${reason}`, null) || ABORTS[reason] || humanize(reason);
  }

  // ---- flow driving --------------------------------------------------------

  async _submit(userInput, scanning) {
    this._renderPending(scanning ? "Scanning your network…" : "Working…", scanning);
    try {
      const step = await submitStep(this._hass, this._flowId, userInput);
      if (this._closed) return;
      this._renderStep(step);
    } catch (err) {
      if (this._closed) return;
      // Expired/unknown flow → restart from the menu.
      if (err && (err.status_code === 404 || err.code === 404)) return this._restart();
      this._renderError(err);
    }
  }

  _restart() {
    this._flowId = null;
    this.open({ store: this._store, menuChoice: this._menuChoice });
  }

  _renderStep(step) {
    this._flowId = step.flow_id || this._flowId;
    switch (step.type) {
      case "menu":
        return this._renderMenu(step);
      case "form":
        return this._renderForm(step);
      case "create_entry":
        this._finished = true;
        return this._renderDone(step);
      case "abort":
        this._finished = true;
        return this._renderAbort(step);
      case "progress":
        return this._renderProgress(step);
      default:
        return this._renderError(new Error(`Unexpected step type “${step.type}”`));
    }
  }

  // ---- renderers -----------------------------------------------------------

  _frame(bodyHtml, { cancel = true } = {}) {
    this.shadowRoot.innerHTML = `
      <style>${tokens}${baseStyles}${buttonStyles}${dialogStyles}
        .options { display:flex; flex-direction:column; gap:10px; margin:6px 0 4px; }
        .opt { display:flex; align-items:center; gap:12px; text-align:left; width:100%;
               background:var(--primary-background-color,#111); border:1px solid var(--mr-line);
               border-radius:12px; padding:14px; cursor:pointer; color:var(--mr-text); font:inherit;
               transition:border-color .15s ease; }
        .opt:hover { border-color:var(--mr-blue); }
        .opt .oic { width:36px; height:36px; border-radius:9px; flex:0 0 auto; background:var(--mr-blue-dim);
                    display:flex; align-items:center; justify-content:center; }
        .opt .oic ha-icon { --mdc-icon-size:20px; color:var(--mr-blue); }
        .opt b { font-weight:600; } .opt small { color:var(--mr-muted); font-size:.8rem; display:block; }
        .spin { display:flex; flex-direction:column; align-items:center; gap:14px; padding:26px 0; }
        .ring { width:38px; height:38px; border:3px solid var(--mr-line); border-top-color:var(--mr-blue);
                border-radius:50%; animation:spin 1s linear infinite; }
        @keyframes spin { to { transform:rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .ring { animation-duration: 2s; } }
        .success { text-align:center; padding:10px 0; }
        .success .big { width:56px; height:56px; border-radius:50%; margin:0 auto 12px; background:var(--mr-blue-dim);
                        display:flex; align-items:center; justify-content:center; }
        .success .big ha-icon { --mdc-icon-size:30px; color:var(--mr-blue); }
        .field { margin-bottom:2px; }
        .field .hint { color:var(--mr-warn); font-size:.72rem; margin-top:3px; }
        .banner { background:color-mix(in srgb, var(--mr-err) 14%, transparent); color:var(--mr-err);
                  border-radius:8px; padding:9px 12px; font-size:.85rem; margin:0 0 12px; }
        input[type="checkbox"] { width:auto; }
      </style>
      <div class="modal" id="ov"><div class="dialog">${bodyHtml}
        <div class="row">
          ${cancel ? `<button class="btn ghost" id="cancel">Cancel</button>` : ""}
          <span id="primary-slot" style="flex:1"></span>
        </div>
      </div></div>`;
    this.shadowRoot.getElementById("ov").onclick = (e) => {
      if (e.target.id === "ov") this.close();
    };
    const c = this.shadowRoot.getElementById("cancel");
    if (c) c.onclick = () => this.close();
  }

  _renderPending(msg, cancellable = false) {
    this._frame(
      `<h3>Add a device</h3>
       <div class="spin"><div class="ring"></div><div class="sub" style="margin:0">${esc(msg)}</div></div>`,
      { cancel: cancellable }
    );
  }

  _renderMenu(step) {
    const ids = this._menuOptionIds(step);
    this._frame(`
      <h3>${esc(this._t("component.multireef.config.step.user.title", "Add to Multi Reef"))}</h3>
      <p class="sub">Pick what you're adding.</p>
      <div class="options">
        ${ids
          .map((id) => {
            const p = MENU_PRESENTATION[id] || {};
            return `<button class="opt" data-opt="${esc(id)}">
              <span class="oic"><ha-icon icon="${esc(p.icon || "mdi:plus")}"></ha-icon></span>
              <span><b>${esc(this._menuLabel(step, id))}</b>${p.blurb ? `<small>${esc(p.blurb)}</small>` : ""}</span>
            </button>`;
          })
          .join("")}
      </div>`);
    this.shadowRoot.querySelectorAll("[data-opt]").forEach((b) => {
      b.onclick = () => this._submit({ next_step_id: b.dataset.opt }, SCAN_STEPS.has(b.dataset.opt));
    });
  }

  _renderForm(step) {
    const fields = normalizeSchema(step.data_schema);
    const baseErr = step.errors?.base;
    this._frame(`
      <h3>${esc(this._stepTitle(step))}</h3>
      ${this._stepDesc(step) ? `<p class="sub">${esc(this._stepDesc(step))}</p>` : ""}
      ${baseErr ? `<div class="banner">${esc(this._errorText(baseErr))}</div>` : ""}
      ${fields.map((f) => this._fieldHtml(step, f)).join("")}
    `);
    // primary Submit button in the row
    const slot = this.shadowRoot.getElementById("primary-slot");
    slot.outerHTML = `<button class="btn" id="submit" style="flex:1">Continue</button>`;
    const submit = () => {
      const input = {};
      for (const f of fields) {
        const el = this.shadowRoot.getElementById(`f-${f.name}`);
        if (!el) continue;
        if (f.kind === "boolean") input[f.name] = el.checked;
        else {
          const v = (el.value ?? "").trim();
          if (v !== "" || f.required) input[f.name] = v;
        }
      }
      const scanning = SCAN_STEPS.has(step.step_id); // e.g. a re-run; forms themselves don't scan
      this._submit(input, scanning);
    };
    this.shadowRoot.getElementById("submit").onclick = submit;
    // Enter submits from a text field.
    this.shadowRoot.querySelectorAll('input[type="text"]').forEach((inp) => {
      inp.onkeydown = (e) => {
        if (e.key === "Enter") submit();
      };
    });
    this.shadowRoot.querySelector("input, select")?.focus();
  }

  _fieldHtml(step, f) {
    const label = esc(this._fieldLabel(step, f.name));
    const err = step.errors?.[f.name];
    const errHtml = err ? `<div class="hint" style="color:var(--mr-err)">${esc(this._errorText(err))}</div>` : "";
    const hint = f.unknown ? `<div class="hint">Unrecognized field — entered as text.</div>` : "";
    if (f.kind === "select") {
      return `<div class="field"><label>${label}</label>
        <select id="f-${esc(f.name)}">${(f.options || [])
        .map(([v, l]) => `<option value="${esc(v)}" ${v === f.default ? "selected" : ""}>${esc(l)}</option>`)
        .join("")}</select>${errHtml}${hint}</div>`;
    }
    if (f.kind === "boolean") {
      return `<div class="field"><label><input type="checkbox" id="f-${esc(f.name)}" ${f.default ? "checked" : ""}> ${label}</label>${errHtml}</div>`;
    }
    const type = f.kind === "number" ? "number" : "text";
    return `<div class="field"><label>${label}</label>
      <input type="${type}" id="f-${esc(f.name)}" value="${f.default != null ? esc(f.default) : ""}">${errHtml}${hint}</div>`;
  }

  _renderProgress(step) {
    this._renderPending("Working on it…", true);
    // Our flow has no progress steps today; if one appears, poll it forward.
    if (this._hass?.connection?.subscribeEvents) {
      this._hass.connection
        .subscribeEvents((ev) => {
          if (ev?.data?.flow_id === this._flowId) this._submit({}, false);
        }, "data_entry_flow_progressed")
        .then((u) => (this._progressUnsub = u))
        .catch(() => {});
    }
  }

  _renderDone(step) {
    const title = step.title || step.result?.title || "your device";
    this._frame(`
      <div class="success">
        <div class="big"><ha-icon icon="mdi:check"></ha-icon></div>
        <h3>Added ${esc(title)}</h3>
        <p class="sub">Its entities appear in a few seconds — the device list refreshes itself.</p>
      </div>`, { cancel: false });
    const slot = this.shadowRoot.getElementById("primary-slot");
    slot.outerHTML = `
      <button class="btn ghost" id="again" style="flex:1">Add another</button>
      <button class="btn" id="done" style="flex:1">Done</button>`;
    this.shadowRoot.getElementById("again").onclick = () => {
      this._flowId = null;
      this._finished = false;
      this.open({ store: this._store, menuChoice: this._menuChoice });
    };
    this.shadowRoot.getElementById("done").onclick = () => {
      fireEvent(this, "wizard-done", {});
      this.close(); // _finished is set, so no abort fires
    };
  }

  _renderAbort(step) {
    this._frame(`
      <h3>Couldn't add that device</h3>
      <p class="sub">${esc(this._abortText(step.reason))}</p>`, { cancel: false });
    const slot = this.shadowRoot.getElementById("primary-slot");
    slot.outerHTML = `
      <button class="btn ghost" id="over" style="flex:1">Start over</button>
      <button class="btn" id="cl" style="flex:1">Close</button>`;
    this.shadowRoot.getElementById("over").onclick = () => this._restart();
    this.shadowRoot.getElementById("cl").onclick = () => this.close();
  }

  _renderError(err) {
    const msg = err?.body?.message || err?.message || "Something went wrong.";
    this._frame(`
      <h3>Something went wrong</h3>
      <div class="banner">${esc(msg)}</div>`, { cancel: false });
    const slot = this.shadowRoot.getElementById("primary-slot");
    slot.outerHTML = `
      <button class="btn ghost" id="retry" style="flex:1">Retry</button>
      <button class="btn" id="cl2" style="flex:1">Close</button>`;
    this.shadowRoot.getElementById("retry").onclick = () => this._restart();
    this.shadowRoot.getElementById("cl2").onclick = () => this.close();
  }
}

if (!customElements.get("mr-wizard")) customElements.define("mr-wizard", MrWizard);
