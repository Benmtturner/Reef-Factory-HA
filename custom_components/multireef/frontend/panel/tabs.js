// <mr-tabs> — the panel's tab bar. Properties: tabs [{id,label,icon}], active.
// Emits "tab-change" {id}. Keyboard: Left/Right cycle, Enter/Space activate.

import { esc, fireEvent } from "./util.js";
import { tokens, baseStyles } from "./styles.js";

class MrTabs extends HTMLElement {
  set tabs(v) {
    this._tabs = v || [];
    this._render();
  }
  set active(id) {
    this._active = id;
    this._render();
  }
  get active() {
    return this._active;
  }

  _render() {
    if (!this._tabs) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        ${tokens}
        ${baseStyles}
        :host { display: block; }
        nav { display: flex; gap: 4px; border-bottom: 1px solid var(--mr-line); }
        button { appearance: none; background: none; border: none; cursor: pointer;
                 font-family: inherit; font-size: .92rem; font-weight: 600;
                 color: var(--mr-muted); padding: 10px 14px 12px;
                 border-bottom: 2px solid transparent; margin-bottom: -1px;
                 display: inline-flex; align-items: center; gap: 8px;
                 transition: color .15s ease, border-color .15s ease; }
        button:hover { color: var(--mr-text); }
        button[aria-selected="true"] { color: var(--mr-blue); border-bottom-color: var(--mr-blue); }
        ha-icon { --mdc-icon-size: 18px; }
        :host([narrow]) button span { display: none; }
      </style>
      <nav role="tablist">
        ${this._tabs
          .map(
            (t) => `
          <button role="tab" data-id="${esc(t.id)}" aria-selected="${t.id === this._active}">
            <ha-icon icon="${esc(t.icon)}"></ha-icon><span>${esc(t.label)}</span>
          </button>`
          )
          .join("")}
      </nav>`;
    this.shadowRoot.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.onclick = () => fireEvent(this, "tab-change", { id: btn.dataset.id });
      btn.onkeydown = (e) => {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        const ids = this._tabs.map((t) => t.id);
        const i = ids.indexOf(btn.dataset.id);
        const next = ids[(i + (e.key === "ArrowRight" ? 1 : ids.length - 1)) % ids.length];
        fireEvent(this, "tab-change", { id: next });
        // move focus with selection
        setTimeout(() => this.shadowRoot.querySelector(`[data-id="${next}"]`)?.focus(), 0);
      };
    });
  }
}

if (!customElements.get("mr-tabs")) customElements.define("mr-tabs", MrTabs);
