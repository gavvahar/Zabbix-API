"""Shared configuration for the Meraki Zabbix provisioning scripts: env vars,
template names, and tuning macros.

Environment variables (read from the repo-root .env, see .env.example):
  ZABBIX_URL          full JSON-RPC endpoint, e.g. https://zabbix.example.com/api_jsonrpc.php
  ZABBIX_API_TOKEN    API token (Bearer)
  ZABBIX_ORG_HOST     org-level Meraki host name (needed for `rollout`)
  ZABBIX_TEST_HOST    a host with the clone already attached (needed for `test`)
  MERAKI_ORG_ID       Meraki organization id (needed by Network/SSID/Radio
                       Discovery and the AP-health status-poller fallback —
                       without it, every clone/recreate ships with a
                       CHANGE_IF_NEEDED placeholder that must be set by hand)
"""

import os
from dotenv import load_dotenv

load_dotenv()

ZABBIX_URL = os.environ["ZABBIX_URL"].rstrip("/")
ZABBIX_TOKEN = os.environ["ZABBIX_API_TOKEN"]
ORG_HOST = os.environ.get("ZABBIX_ORG_HOST", "").strip()
TEST_HOST = os.environ.get("ZABBIX_TEST_HOST", "").strip()
MERAKI_ORG_ID = os.environ.get("MERAKI_ORG_ID", "").strip() or "CHANGE_IF_NEEDED"

SOURCE_TEMPLATE = "Cisco Meraki device by HTTP"
CLONE_TEMPLATE = "Cisco Meraki device by HTTP - Packet Loss"
DASHBOARD_TEMPLATE = "Cisco Meraki dashboard by HTTP"
DASHBOARD_CLONE_TEMPLATE = "Cisco Meraki dashboard by HTTP - Wireless Health"
DISCOVERY_RULE_NAME = "Devices discovery"

# {$MERAKI.ORG.ID} does NOT already exist on either the device or dashboard
# official templates (they discover organizations/devices via their own LLD
# rules instead of a static org id) — org-scoped calls in scripts.py (device
# status poller, Network/SSID/Radio Discovery) need a real value here, or
# Zabbix sends the literal unresolved macro text and Meraki's API 404s.
DEVICE_MACROS = {
    "{$MERAKI.PING.COUNT}": "5",
    "{$MERAKI.PING.INTERVAL}": "5m",
    "{$MERAKI.PING.TARGET}": "8.8.8.8",
    "{$MERAKI.PING.LOSS}": "20",
    "{$MERAKI.PING.LATENCY.HIGH}": "100",  # ms
    "{$MERAKI.DEVICESTATUS.INTERVAL}": "5m",
    "{$MERAKI.FIRMWARE.EXPECTED}": "",  # blank = Firmware Outdated trigger stays inactive until set
    "{$MERAKI.ORG.ID}": MERAKI_ORG_ID,
}

DASHBOARD_MACROS = {
    "{$MERAKI.LLD.INTERVAL}": "1h",
    "{$MERAKI.CLIENTCOUNT.HIGH}": "50",
    "{$MERAKI.AUTHFAIL.HIGH}": "20",
    "{$MERAKI.AUTHFAIL.SSID.HIGH}": "10",
    "{$MERAKI.ORG.ID}": MERAKI_ORG_ID,
}

TRIGGER_DESCRIPTION = "Meraki: Packet loss to {$MERAKI.PING.TARGET} > {$MERAKI.PING.LOSS}%"
