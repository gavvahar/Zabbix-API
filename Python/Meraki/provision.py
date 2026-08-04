#!/usr/bin/env python3
"""
Provision Meraki wireless monitoring in Zabbix via the API.

Automates instructions.md plus the wireless-health follow-up list end to end:
  all         -> runs create, ap-health, and wireless in sequence
  create      -> Steps 1-5: clone the device template, add macros, create the
                 packet loss script item + dependent items + trigger
  ap-health   -> extends the device clone: device status poll, AP Down,
                 Firmware Outdated, High Latency, API Failure
  wireless    -> clones the dashboard template and adds Network/SSID/Radio
                 Discovery plus their trigger prototypes (High Client Count,
                 Authentication Failure Rate, Wireless Health Degraded)
  test        -> Step 6: force-run the packet loss item on one real host and
                 print the raw JSON, without ever re-typing the API token
  rollout     -> Step 7B: repoint the device-discovery host prototype at the
                 clone and force an immediate re-sync (fleet-wide, deliberate)
  rollback    -> undoes rollout

`test`, `rollout`, and `rollback` touch a real host or the fleet-wide discovery
rule, so they're deliberately left out of `all` — run them one at a time.

Requires Zabbix 6.4+ (Script item type, item-level timeout override,
task.create check-now). Requires `requests` (pip install requests) and a
Zabbix API token (Users > API tokens) with read/write on the relevant hosts.

Environment variables:
  ZABBIX_URL          e.g. https://zabbix.example.com
  ZABBIX_API_TOKEN    API token (Bearer)
  ZABBIX_ORG_HOST     org-level Meraki host name (needed for `rollout`)
  ZABBIX_TEST_HOST    a host with the clone already attached (needed for `test`)

NOT built here — "AP Discovery" from the follow-up list:
The official dashboard template already discovers one host per device via
its "Devices discovery" LLD rule (see DISCOVERY_RULE_NAME in
config.py). A second discovery rule that also creates per-AP hosts
would collide with those (duplicate host errors). AP-level metrics (status,
firmware, latency) are instead added as static items on the device template
clone — same pattern as the existing packet loss item — since every
discovered host already carries {$SERIAL}. See aphealth.py.

Meraki endpoint/field names used across the scripts (devices/statuses,
wireless/ssids, wireless/failedConnections,
wireless/devices/channelUtilization/byDevice) are best-effort from the
public Dashboard API v1 and were NOT verified against a live org — check
field names/response shape against current Meraki docs before running
against production. Thresholds are placeholder macros (see
config.py) — tune per your environment.

Implementation is split across sibling modules:
  config.py     env vars, template names, tuning macros
  scripts.py    Zabbix Script item JavaScript bodies
  api.py        Zabbix JSON-RPC wrapper + lookup helpers
  create.py     `create` action
  aphealth.py   `ap-health` action
  wireless.py   `wireless` action
  ops.py        `test` / `rollout` / `rollback` actions
"""

import sys

from create import main
from aphealth import main_ap_health
from wireless import create_wireless_health
from ops import test_item, rollout, rollback


def main_all():
    """Run `create`, `ap-health`, and `wireless` in sequence."""
    main()
    main_ap_health()
    create_wireless_health()


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    {
        "all": main_all,
        "create": main,
        "ap-health": main_ap_health,
        "wireless": create_wireless_health,
        "test": test_item,
        "rollout": rollout,
        "rollback": rollback,
    }.get(
        action,
        lambda: print("Usage: python provision.py [all|create|ap-health|wireless|test|rollout|rollback]"),
    )()
