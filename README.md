# Reef Factory KH Keeper for Home Assistant

A local, cloud-free Home Assistant integration for the [Reef Factory](https://reeffactory.com)
KH Keeper. It talks to the device directly on your LAN over WebSocket — no Reef Factory
account, no polling (`local_push`).

> ⚠️ Unofficial and not affiliated with Reef Factory. The device's local API has **no
> authentication**, so anyone on the same network can read it and issue commands — keep your
> reef gear on a trusted network/VLAN. Use at your own risk; this controls hardware attached
> to a live aquarium.

## Features

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
| Measure Now | button — starts a measurement |
| Cancel Measurement | button — cancels the run in progress |

## Installation

**HACS (custom repository):** add this repository as an Integration, install, and restart
Home Assistant.

**Manual:** copy `custom_components/reef_factory_kh/` into your Home Assistant
`config/custom_components/` directory and restart.

## Setup

Settings → Devices & Services → Add Integration → *Reef Factory KH Keeper*.

The integration scans your Home Assistant host's network and offers any KH Keepers it finds
— just pick yours, no IP typing. If none are found (e.g. the device is on a separate VLAN),
it falls back to manual IP entry. Reserving a static IP for the device in your router is
recommended.

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
