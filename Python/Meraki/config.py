"""Shared configuration for the Meraki Zabbix provisioning scripts: env vars,
template names, and tuning macros.

Environment variables (read from the repo-root .env, see .env.example):
  ZABBIX_URL          full JSON-RPC endpoint, e.g. https://zabbix.example.com/api_jsonrpc.php
  ZABBIX_API_TOKEN    API token (Bearer)
  ZABBIX_ORG_HOST     org-level Meraki host name (needed for `rollout`)
  ZABBIX_TEST_HOST    a host with the clone already attached (needed for `test`)
"""

import os
from dotenv import load_dotenv

load_dotenv()

ZABBIX_URL = os.environ["ZABBIX_URL"].rstrip("/")
ZABBIX_TOKEN = os.environ["ZABBIX_API_TOKEN"]
ORG_HOST = os.environ.get("ZABBIX_ORG_HOST", "").strip()
TEST_HOST = os.environ.get("ZABBIX_TEST_HOST", "").strip()

SOURCE_TEMPLATE = "Cisco Meraki device by HTTP"
CLONE_TEMPLATE = "Cisco Meraki device by HTTP - Packet Loss"
DASHBOARD_TEMPLATE = "Cisco Meraki dashboard by HTTP"
DASHBOARD_CLONE_TEMPLATE = "Cisco Meraki dashboard by HTTP - Wireless Health"
DISCOVERY_RULE_NAME = "Get data: Devices discovery"

# {$MERAKI.ORG.ID} is assumed to already exist on the dashboard template
# (org-scoped calls need it) — reuse it, same as {$MERAKI.API.URL} / {$MERAKI.TOKEN}.
DEVICE_MACROS = {
    "{$MERAKI.PING.COUNT}": "5",
    "{$MERAKI.PING.INTERVAL}": "5m",
    "{$MERAKI.PING.TARGET}": "8.8.8.8",
    "{$MERAKI.PING.LOSS}": "20",
    "{$MERAKI.PING.LATENCY.HIGH}": "100",  # ms
    "{$MERAKI.DEVICESTATUS.INTERVAL}": "5m",
    "{$MERAKI.FIRMWARE.EXPECTED}": "",  # blank = Firmware Outdated trigger stays inactive until set
}

DASHBOARD_MACROS = {
    "{$MERAKI.LLD.INTERVAL}": "1h",
    "{$MERAKI.CLIENTCOUNT.HIGH}": "50",
    "{$MERAKI.AUTHFAIL.HIGH}": "20",
    "{$MERAKI.AUTHFAIL.SSID.HIGH}": "10",
}

TRIGGER_DESCRIPTION = "Meraki: Packet loss to {$MERAKI.PING.TARGET} > {$MERAKI.PING.LOSS}%"
