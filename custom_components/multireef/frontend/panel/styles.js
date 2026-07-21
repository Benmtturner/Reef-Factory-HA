// Multi Reef panel — shared style strings.
//
// Rules (house standard + ui-ux-pro-max checklist): HA theme variables only
// (no hardcoded palettes beyond the brand blue), mdi ha-icons (never emoji),
// visible keyboard focus, stable 150-300ms hover transitions, reduced-motion
// respected, z-scale sticky:10 / popover:20 / overlay:50.

export const tokens = `
  :host {
    --mr-blue: #3f8fd6;
    --mr-blue-dim: color-mix(in srgb, var(--mr-blue) 16%, transparent);
    --mr-surface: var(--card-background-color, #1c1f24);
    --mr-line: var(--divider-color, #444);
    --mr-text: var(--primary-text-color, #eee);
    --mr-muted: var(--secondary-text-color, #9aa0a8);
    --mr-ok: var(--success-color, #3fae5a);
    --mr-err: var(--error-color, #e2574c);
    --mr-warn: var(--warning-color, #e5a33d);
    --mr-radius: 14px;
    --mr-z-sticky: 10;
    --mr-z-popover: 20;
    --mr-z-overlay: 50;
  }
`;

export const baseStyles = `
  [hidden] { display: none !important; }
  *:focus-visible { outline: 2px solid var(--mr-blue); outline-offset: 2px; border-radius: 4px; }
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
  }
  .sec-label { text-transform: uppercase; letter-spacing: .08em; font-size: .72rem;
               color: var(--mr-muted); margin: 26px 4px 12px; font-weight: 600; }
`;

export const buttonStyles = `
  .btn { background: var(--mr-blue); color: #fff; border: none; border-radius: 8px;
         padding: 10px 14px; font-size: .88rem; font-weight: 500; cursor: pointer;
         font-family: inherit; transition: filter .15s ease, transform .08s ease; }
  .btn:hover { filter: brightness(1.08); }
  .btn:active { transform: translateY(1px); }
  .btn.ghost { background: transparent; color: var(--mr-blue); border: 1px solid var(--mr-blue); }
  .btn[disabled] { opacity: .5; cursor: default; filter: none; transform: none; }
`;

export const dialogStyles = `
  .modal { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: flex;
           align-items: center; justify-content: center; z-index: var(--mr-z-overlay, 50);
           padding: 16px; }
  .dialog { background: var(--ha-card-background, var(--mr-surface));
            border-radius: var(--mr-radius); padding: 22px; width: min(94vw, 440px);
            max-height: 88vh; overflow-y: auto; box-sizing: border-box;
            box-shadow: 0 16px 50px rgba(0,0,0,.5); }
  @media (max-width: 600px) {
    .modal { padding: 10px; align-items: flex-end; }
    .dialog { width: 100%; max-height: 92vh; border-radius: 14px 14px 0 0; }
  }
  .dialog h3 { margin: 0 0 4px; font-size: 1.15rem; }
  .dialog .sub { color: var(--mr-muted); font-size: .85rem; margin: 0 0 16px; }
  .dialog label { display: block; font-size: .74rem; text-transform: uppercase;
                  letter-spacing: .05em; color: var(--mr-muted); margin: 12px 0 5px; }
  .dialog select, .dialog input[type="text"] {
    width: 100%; box-sizing: border-box; padding: 10px; border-radius: 8px;
    border: 1px solid var(--mr-line); font-size: .95rem; font-family: inherit;
    background: var(--primary-background-color, #111); color: var(--mr-text); }
  .row { display: flex; gap: 10px; margin-top: 20px; }
  .row .btn { flex: 1; }
  .status { margin-top: 14px; font-size: .85rem; min-height: 1.2em; }
  .status.ok { color: var(--mr-ok); }
  .status.err { color: var(--mr-err); }
  .status.warn { color: var(--mr-warn); }
`;
