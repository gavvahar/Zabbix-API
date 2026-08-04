"""`create` action — Steps 1-5: clone the device template, add macros, and
create the packet loss script item + dependent items + trigger.
"""

import json

from meraki_api import api_call, get_template_id, strip_uuids, add_macros
from meraki_config import SOURCE_TEMPLATE, CLONE_TEMPLATE, DEVICE_MACROS, TRIGGER_DESCRIPTION
from meraki_scripts import SCRIPT_BODY


def clone_template():
    existing = api_call("template.get", {"filter": {"host": [CLONE_TEMPLATE]}})
    if existing:
        print(f"'{CLONE_TEMPLATE}' already exists, skipping clone.")
        return existing[0]["templateid"]

    print(f"Cloning '{SOURCE_TEMPLATE}' -> '{CLONE_TEMPLATE}'")
    src_id = get_template_id(SOURCE_TEMPLATE)
    exported = api_call("configuration.export", {"format": "json", "options": {"templates": [src_id]}})
    data = json.loads(exported)
    tmpl = data["zabbix_export"]["templates"][0]
    tmpl["template"] = CLONE_TEMPLATE
    tmpl["name"] = CLONE_TEMPLATE
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
    return get_template_id(CLONE_TEMPLATE)


def create_script_item(templateid):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": "meraki.get.packetloss"}})
    if found:
        return found[0]["itemid"]

    print("Creating 'Get packet loss data' script item")
    result = api_call(
        "item.create",
        {
            "hostid": templateid,
            "name": "Get packet loss data",
            "key_": "meraki.get.packetloss",
            "type": 21,  # Script
            "value_type": 4,  # Text
            "delay": "{$MERAKI.PING.INTERVAL};50s/1-7,00:00-24:00",
            "timeout": "{$MERAKI.DATA.TIMEOUT}",
            "history": "0",  # Do not store
            "params": SCRIPT_BODY,
            "parameters": [
                {"name": "count", "value": "{$MERAKI.PING.COUNT}"},
                {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
                {"name": "serial", "value": "{$SERIAL}"},
                {"name": "target", "value": "{$MERAKI.PING.TARGET}"},
                {"name": "token", "value": "{$MERAKI.TOKEN}"},
                {"name": "url", "value": "{$MERAKI.API.URL}"},
            ],
        },
    )
    return result["itemids"][0]


def create_dependent_item(templateid, master_itemid, name, key, jsonpath, units):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating dependent item '{name}'")
    result = api_call(
        "item.create",
        {
            "hostid": templateid,
            "name": name,
            "key_": key,
            "type": 18,  # Dependent item
            "master_itemid": master_itemid,
            "value_type": 0,  # Numeric float
            "units": units,
            "history": "31d",
            "trends": "365d",
            "preprocessing": [
                {
                    "type": 12,  # JSONPath
                    "params": jsonpath,
                    "error_handler": 1,  # Discard value
                    "error_handler_params": "",
                }
            ],
        },
    )
    return result["itemids"][0]


def create_trigger(templateid):
    found = api_call("trigger.get", {"hostids": [templateid], "filter": {"description": TRIGGER_DESCRIPTION}})
    if found:
        return found[0]["triggerid"]

    print("Creating packet loss trigger")
    expression = f"min(/{CLONE_TEMPLATE}/meraki.device.packetloss.pct,#3)>{{$MERAKI.PING.LOSS}}"
    result = api_call(
        "trigger.create",
        {
            "description": TRIGGER_DESCRIPTION,
            "expression": expression,
            "priority": 2,  # Warning
            "tags": [{"tag": "scope", "value": "performance"}],
        },
    )
    return result["triggerids"][0]


def main():
    templateid = clone_template()
    add_macros(templateid, DEVICE_MACROS)
    script_itemid = create_script_item(templateid)
    create_dependent_item(
        templateid,
        script_itemid,
        "Latency, ms",
        "meraki.device.ping.latency",
        "$.result.results.latencies.average",
        "ms",
    )
    create_dependent_item(
        templateid,
        script_itemid,
        "Packet loss, %",
        "meraki.device.packetloss.pct",
        "$.result.results.loss.percentage",
        "%",
    )
    create_trigger(templateid)
    print(f"Done. '{CLONE_TEMPLATE}' is ready (templateid {templateid}).")
    print("Next: run `ap-health`, attach it to a test host and run `test`, then `rollout` when ready.")
