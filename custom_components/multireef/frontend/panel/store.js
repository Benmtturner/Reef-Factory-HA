// MultiReefStore — the panel's data layer.
//
// Fetches HA's device/entity/area registries + our config entries once over the
// WebSocket API, indexes them, derives a brand→model→device tree (+ bridges),
// and keeps it fresh on registry-change events. Per-device online status is
// diffed from hass.states on each hass push (debounced) and emitted separately
// so views patch status dots in place without re-rendering the tree.
//
// Events (CustomEvent):
//   "ready"          — first successful load
//   "tree-changed"   — registries changed → re-render groups
//   "status-changed" {deviceIds:[]} — some devices' online status flipped
//   "error"          — initial load failed (will auto-retry once)

import { debounce } from "./util.js";
import { brandFor, isInfrastructure, modelMeta, cardFor, BRANDS } from "./catalog.js";

const OFFLINE = new Set(["unavailable", "unknown", "", undefined, null]);

export class MultiReefStore extends EventTarget {
  constructor(domain = "multireef") {
    super();
    this._domain = domain;
    this._ready = false;
    this._unsub = [];
    this._statusSig = new Map(); // device_id -> status string
    this._diffStatus = debounce(() => this._runStatusDiff(), 200);
    this._refetch = debounce(() => this._reload(), 250);
  }

  get ready() {
    return this._ready;
  }
  get tree() {
    return this._tree || [];
  }
  get bridges() {
    return this._bridges || [];
  }
  get areas() {
    return this._areasSorted || [];
  }
  get counts() {
    return this._counts || { devices: 0, unavailable: 0, updatesAvailable: 0 };
  }
  get hass() {
    return this._hass;
  }
  set hass(hass) {
    this._hass = hass;
    if (this._ready) this._diffStatus();
  }
  deviceById(id) {
    return this._devById?.get(id);
  }

  // ---- lifecycle -----------------------------------------------------------

  async init(hass) {
    this._hass = hass;
    if (this._initing) return;
    this._initing = true;
    try {
      await this._reload();
      this._ready = true;
      this._subscribe();
      this.dispatchEvent(new CustomEvent("ready"));
    } catch (err) {
      this.dispatchEvent(new CustomEvent("error", { detail: { err } }));
      // one auto-retry — registries can lag right at startup
      if (!this._retried) {
        this._retried = true;
        setTimeout(() => {
          this._initing = false;
          this.init(this._hass);
        }, 3000);
      }
    } finally {
      if (this._ready) this._initing = false;
    }
  }

  async refresh() {
    await this._reload();
  }

  dispose() {
    this._unsub.forEach((u) => {
      try {
        u();
      } catch (_) {}
    });
    this._unsub = [];
  }

  _subscribe() {
    if (!this._hass?.connection?.subscribeEvents) return;
    const evts = ["device_registry_updated", "entity_registry_updated", "area_registry_updated"];
    for (const evt of evts) {
      this._hass.connection
        .subscribeEvents(() => this._refetch(), evt)
        .then((u) => this._unsub.push(u))
        .catch(() => {});
    }
  }

  // ---- fetch + build -------------------------------------------------------

  async _reload() {
    const hass = this._hass;
    const [entries, devices, entities, areas] = await Promise.all([
      hass.callWS({ type: "config_entries/get", domain: this._domain }),
      hass.callWS({ type: "config/device_registry/list" }),
      hass.callWS({ type: "config/entity_registry/list" }),
      hass.callWS({ type: "config/area_registry/list" }),
    ]);
    // Defensive: the WS get is domain-filtered server-side, but only trust ours.
    this._entryIds = new Set(
      (entries || []).filter((e) => e.domain === this._domain).map((e) => e.entry_id)
    );
    this._areaName = new Map((areas || []).map((a) => [a.area_id, a.name]));
    this._areasSorted = (areas || [])
      .map((a) => ({ area_id: a.area_id, name: a.name }))
      .sort((a, b) => a.name.localeCompare(b.name));

    // Entities owned by us, grouped by device.
    const entsByDevice = new Map();
    for (const e of entities || []) {
      const ours = e.config_entry_id ? this._entryIds.has(e.config_entry_id) : e.platform === this._domain;
      if (!ours || !e.device_id) continue;
      const rec = {
        entity_id: e.entity_id,
        domain: e.entity_id.split(".")[0],
        disabled: !!e.disabled_by,
      };
      (entsByDevice.get(e.device_id) || entsByDevice.set(e.device_id, []).get(e.device_id)).push(rec);
    }

    // Devices owned by us.
    this._devById = new Map();
    const owned = [];
    for (const d of devices || []) {
      const ours = (d.config_entries || []).some((id) => this._entryIds.has(id));
      if (!ours) continue;
      const dv = {
        id: d.id,
        name: d.name_by_user || d.name || "Device",
        rawName: d.name,
        manufacturer: d.manufacturer || "",
        model: d.model || "",
        areaId: d.area_id || null,
        areaName: d.area_id ? this._areaName.get(d.area_id) || null : null,
        viaDeviceId: d.via_device_id || null,
        entities: entsByDevice.get(d.id) || [],
      };
      dv.isBridge = isInfrastructure(dv.manufacturer);
      dv.cardMeta = cardFor(dv.manufacturer, dv.model) || null;
      this._devById.set(dv.id, dv);
      owned.push(dv);
    }

    this._buildTree(owned);
    this._buildBridges(owned);
    this._statusSig = new Map(); // force a fresh status pass
    this._runStatusDiff(true);
    this._counts = {
      devices: owned.filter((d) => !d.isBridge).length,
      unavailable: owned.filter((d) => !d.isBridge && this._statusSig.get(d.id) === "unavailable").length,
      updatesAvailable: (this._bridges || []).filter((b) => b.updateAvailable).length,
    };
    this.dispatchEvent(new CustomEvent("tree-changed"));
  }

  _buildTree(owned) {
    const brandOrder = new Map(BRANDS.map((b, i) => [b.manufacturer, i]));
    const groups = new Map(); // brand key -> {brand, models:Map}
    for (const dv of owned) {
      if (dv.isBridge) continue;
      const brand = brandFor(dv.manufacturer) || {
        id: "other:" + dv.manufacturer,
        label: dv.manufacturer || "Other",
        icon: "mdi:help-circle-outline",
        _other: true,
      };
      const gkey = brand.id;
      let g = groups.get(gkey);
      if (!g) {
        g = { brand: { id: brand.id, label: brand.label, icon: brand.icon }, models: new Map(), order: brandOrder.has(dv.manufacturer) ? brandOrder.get(dv.manufacturer) : 999 };
        groups.set(gkey, g);
      }
      const modelName = dv.model || "Device";
      let m = g.models.get(modelName);
      if (!m) {
        m = { model: modelName, icon: modelMeta(dv.manufacturer, dv.model)?.icon || brand.icon, devices: [] };
        g.models.set(modelName, m);
      }
      m.devices.push(dv);
    }
    this._tree = [...groups.values()]
      .sort((a, b) => a.order - b.order || a.brand.label.localeCompare(b.brand.label))
      .map((g) => ({
        brand: g.brand,
        count: [...g.models.values()].reduce((n, m) => n + m.devices.length, 0),
        models: [...g.models.values()]
          .sort((a, b) => a.model.localeCompare(b.model))
          .map((m) => ({
            ...m,
            count: m.devices.length,
            devices: m.devices.sort((a, b) => a.name.localeCompare(b.name)),
          })),
      }));
  }

  _buildBridges(owned) {
    const bridges = [];
    for (const dv of owned) {
      if (!dv.isBridge) continue;
      const updateEnt = dv.entities.find((e) => e.domain === "update" && !e.disabled);
      const childCount = owned.filter((o) => o.viaDeviceId === dv.id).length;
      bridges.push({ device: dv, updateEntityId: updateEnt?.entity_id || null, childCount });
    }
    this._bridges = bridges;
    this._refreshBridgeState(); // fill installed/latest/updateAvailable from states
  }

  // Live firmware fields (from hass.states) — refreshed on each status diff too.
  _refreshBridgeState() {
    const states = this._hass?.states || {};
    for (const b of this._bridges || []) {
      const st = b.updateEntityId ? states[b.updateEntityId] : undefined;
      const a = st?.attributes || {};
      b.installed = a.installed_version;
      b.latest = a.latest_version;
      b.updateAvailable = st?.state === "on";
      b.inProgress = !!a.in_progress;
    }
  }

  // ---- status diff (cheap, per hass push) ----------------------------------

  _deviceStatus(dv) {
    const states = this._hass?.states || {};
    let any = false;
    let online = false;
    for (const e of dv.entities) {
      if (e.disabled) continue;
      any = true;
      const s = states[e.entity_id]?.state;
      if (!OFFLINE.has(s)) {
        online = true;
        break;
      }
    }
    if (!any) return "unknown";
    return online ? "ok" : "unavailable";
  }

  _runStatusDiff(silent = false) {
    if (!this._devById) return;
    this._refreshBridgeState();
    const changed = [];
    for (const dv of this._devById.values()) {
      let sig = this._deviceStatus(dv);
      if (dv.isBridge) {
        // Bridges also re-render on firmware state; fold it into the signature.
        const b = this._bridges.find((x) => x.device.id === dv.id);
        sig += `|${b?.installed}|${b?.latest}|${b?.updateAvailable}|${b?.inProgress}`;
      }
      dv.status = sig.split("|")[0];
      if (this._statusSig.get(dv.id) !== sig) {
        this._statusSig.set(dv.id, sig);
        changed.push(dv.id);
      }
    }
    if (changed.length && !silent) {
      this.dispatchEvent(new CustomEvent("status-changed", { detail: { deviceIds: changed } }));
    }
  }

  // ---- card entity resolution ---------------------------------------------

  /** Pick the card's `entity` from a device's own entities via catalog anchor. */
  anchorEntityFor(dv) {
    const anchor = dv.cardMeta?.anchor;
    if (!anchor) return null;
    const hit = dv.entities.find(
      (e) => !e.disabled && e.domain === anchor.domain && e.entity_id.includes(anchor.keyword)
    );
    return hit?.entity_id || null;
  }

  // ---- actions -------------------------------------------------------------

  rename(deviceId, name) {
    return this._hass.callWS({
      type: "config/device_registry/update",
      device_id: deviceId,
      name_by_user: name || null,
    });
  }
  setArea(deviceId, areaId) {
    return this._hass.callWS({
      type: "config/device_registry/update",
      device_id: deviceId,
      area_id: areaId || null,
    });
  }
  async createArea(name) {
    const area = await this._hass.callWS({ type: "config/area_registry/create", name });
    return area.area_id;
  }
}
