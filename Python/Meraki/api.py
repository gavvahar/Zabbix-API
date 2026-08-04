"""Thin wrapper around the Zabbix JSON-RPC API plus lookup/config helpers
shared by every provisioning step (create, ap-health, wireless, ops).
"""

import json, requests
from config import ZABBIX_URL, ZABBIX_TOKEN


def api_call(method, params=None):
    """Call a Zabbix API method over JSON-RPC and return its result."""
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
    """Look up a template's id by name, raising if it doesn't exist."""
    result = api_call("template.get", {"filter": {"host": [name]}, "output": ["templateid"]})
    if not result:
        raise RuntimeError(f"Template not found: {name}")
    return result[0]["templateid"]


def get_host_id(name):
    """Look up a host's id by its technical or visible name, or None if not found."""
    for key in ("host", "name"):
        result = api_call("host.get", {"filter": {key: [name]}, "output": ["hostid"]})
        if result:
            return result[0]["hostid"]
    return None


def strip_uuids(obj):
    """Recursively strip 'uuid' keys from a decoded configuration export, in place."""
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


def clone_template(source_name, clone_name):
    """Clone source_name to clone_name via export/import, or return the existing clone's id."""
    existing = api_call("template.get", {"filter": {"host": [clone_name]}})
    if existing:
        print(f"'{clone_name}' already exists, skipping clone.")
        return existing[0]["templateid"]

    print(f"Cloning '{source_name}' -> '{clone_name}'")
    src_id = get_template_id(source_name)
    exported = api_call("configuration.export", {"format": "json", "options": {"templates": [src_id]}})
    data = json.loads(exported)
    tmpl = data["zabbix_export"]["templates"][0]
    tmpl["template"] = clone_name
    tmpl["name"] = clone_name
    strip_uuids(data["zabbix_export"])

    rules = {
        "template_groups": {"createMissing": True},
        "templates": {"createMissing": True, "updateExisting": False},
        "templateLinkage": {"createMissing": True},
        "items": {"createMissing": True, "updateExisting": False},
        "triggers": {"createMissing": True, "updateExisting": False},
        "discoveryRules": {"createMissing": True, "updateExisting": False},
        "graphs": {"createMissing": True, "updateExisting": False},
        "valueMaps": {"createMissing": True, "updateExisting": False},
    }
    api_call("configuration.import", {"format": "json", "source": json.dumps(data), "rules": rules})
    return get_template_id(clone_name)


def add_macros(templateid, macros):
    """Create any of the given user macros that aren't already defined on the template."""
    existing = {m["macro"] for m in api_call("usermacro.get", {"hostids": [templateid], "output": ["macro"]})}
    for macro, value in macros.items():
        if macro in existing:
            continue
        print(f"Adding macro {macro}")
        api_call("usermacro.create", {"hostid": templateid, "macro": macro, "value": value})
