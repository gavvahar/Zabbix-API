"""Thin wrapper around the Zabbix JSON-RPC API plus lookup/config helpers
shared by every provisioning step (create, ap-health, wireless, ops).
"""

import json
import requests

from meraki_config import ZABBIX_URL, ZABBIX_TOKEN


def api_call(method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    headers = {
        "Content-Type": "application/json-rpc",
        "Authorization": f"Bearer {ZABBIX_TOKEN}",
    }
    resp = requests.post(ZABBIX_URL, headers=headers, data=json.dumps(payload), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"{method} failed: {data['error']}")
    return data["result"]


def get_template_id(name):
    result = api_call("template.get", {"filter": {"host": [name]}, "output": ["templateid"]})
    if not result:
        raise RuntimeError(f"Template not found: {name}")
    return result[0]["templateid"]


def get_host_id(name):
    for key in ("host", "name"):
        result = api_call("host.get", {"filter": {key: [name]}, "output": ["hostid"]})
        if result:
            return result[0]["hostid"]
    return None


def strip_uuids(obj):
    # Zabbix matches templates by uuid before name; keeping the source
    # template's uuid on the renamed copy makes import treat it as the
    # same template and conflict with the original.
    if isinstance(obj, dict):
        obj.pop("uuid", None)
        for v in obj.values():
            strip_uuids(v)
    elif isinstance(obj, list):
        for item in obj:
            strip_uuids(item)


def add_macros(templateid, macros):
    existing = {m["macro"] for m in api_call("usermacro.get", {"hostids": [templateid], "output": ["macro"]})}
    for macro, value in macros.items():
        if macro in existing:
            continue
        print(f"Adding macro {macro}")
        api_call("usermacro.create", {"hostid": templateid, "macro": macro, "value": value})
