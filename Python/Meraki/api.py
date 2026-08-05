"""Thin wrapper around the Zabbix JSON-RPC API plus lookup/config helpers
shared by every provisioning step (create, ap-health, wireless, ops).
"""

import json, uuid, requests
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


def rewrite_host_refs(obj, source_name, clone_name):
    """Recursively replace literal occurrences of source_name with clone_name in
    every string value within a decoded configuration export subtree, in place.

    Zabbix embeds the template's own technical name as plain text inside trigger
    (and trigger prototype) expressions — e.g. "/{HOST}/{KEY}" — and inside
    dashboard widget graph references, not just in the template's own "template"/
    "name" fields. Left unrewritten, those references still resolve to the
    source template on import, so Zabbix matches new trigger prototypes against
    objects that already exist there and rejects them as duplicates.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                obj[k] = v.replace(source_name, clone_name)
            else:
                rewrite_host_refs(v, source_name, clone_name)
    elif isinstance(obj, list):
        for item in obj:
            rewrite_host_refs(item, source_name, clone_name)


def reset_uuids(obj):
    """Recursively replace 'uuid' values with freshly generated ones within a
    decoded configuration export subtree, in place, so Zabbix treats the
    renamed copy as new objects instead of matching the source template's by
    uuid. Zabbix's own uuids are 32-char hex strings (no dashes); an empty or
    missing tag fails its import validation, so a real replacement is required.

    Callers should scope this to the export's "templates" subtree only —
    other top-level sections like "host_groups" reference existing objects by
    uuid and need their real value kept, or the group match — and import
    validation — fails.
    """
    if isinstance(obj, dict):
        if "uuid" in obj:
            obj["uuid"] = uuid.uuid4().hex
        for v in obj.values():
            reset_uuids(v)
    elif isinstance(obj, list):
        for item in obj:
            reset_uuids(item)


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
    rewrite_host_refs(data["zabbix_export"]["templates"], source_name, clone_name)
    reset_uuids(data["zabbix_export"]["templates"])

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
