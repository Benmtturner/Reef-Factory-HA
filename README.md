# Reef Factory for Home Assistant

A local, cloud-free Home Assistant integration for [Reef Factory](https://reeffactory.com)
reef-tank devices. It talks to each device directly on your LAN over WebSocket — no Reef
Factory account, no polling (`local_push`).

**Supported devices** (auto-detected by serial):

- **KH Keeper** (`RFKH`) — carbonate-hardness monitor + control
- **Single-head doser** (`RFDP`) — reservoir level and dose schedule

> ⚠️ Unofficial and not affiliated with Reef Factory. The device's local API has **no
> authentication**, so anyone on the same network can read it and issue commands — keep your
> reef gear on a trusted network/VLAN. Use at your own risk; this controls hardware attached
> to a live aquarium.

## Features

### KH Keeper

| Entity | Detail |
|---|---|
| Carbonate Hardness | current dKH, with change and recent history as attributes |
| pH | pH at the most recent measurement |
| Last Measurement | timestamp of the most recent measurement |
| Measurement Status | live state (Idle / Measuring / Cancelling / Re-measuring) + progress % |
| Reagent Alert | binary "problem" sensor from the device's reagent-low flag |
| KH Out of Range | binary "problem" sensor — KH outside the configured alert band |
| Alert Low / Alert High | the configured alert thresholds |
| Remaining Reagent | **settable** number (mL) — shows the live value and lets you set it after a refill |
| Measure Now / Cancel Measurement | buttons — start or cancel a measurement |

### Single-head doser

| Entity | Detail |
|---|---|
| Container Level | current reservoir volume (mL) |
| Reservoir | reservoir fill (%) |
| Capacity | reservoir capacity (mL, diagnostic) |
| Daily Dose Total | total volume dosed per day (mL) |
| Number of Doses | number of scheduled doses per day |
| Per-Dose Amount | volume of each scheduled dose (mL) |
| Last Dose | volume of the most recent dose (mL) and its timestamp |
| Dosing | binary "running" sensor — on while the pump is dispensing |

## Installation

**HACS (custom repository):** add this repository as an Integration, install, and restart
Home Assistant.

**Manual:** copy `custom_components/reef_factory_kh/` into your Home Assistant
`config/custom_components/` directory and restart.

## Setup

Settings → Devices & Services → Add Integration → *Reef Factory*.

The integration scans your Home Assistant host's network and offers any supported Reef Factory
devices it finds — just pick yours, no IP typing. Add each device (KH Keeper, doser) as its own
entry. If none are found (e.g. the device is on a separate VLAN), it falls back to manual IP entry.

**A static IP is not required.** If a device reboots and DHCP gives it a new address, the
integration relearns it automatically — by MAC via Home Assistant's discovery, and by a
network rescan for the device's serial as a fallback.

## Example automation — alert on a KH excursion

```yaml
automation:
  - alias: "Reef KH too high"
    trigger:
      - platform: state
        entity_id: binary_sensor.kh_keeper_kh_out_of_range
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "KH is {{ states('sensor.kh_keeper_carbonate_hardness') }} dKH — out of range."
```

## License

MIT — see [LICENSE](LICENSE).
