"""`create` action — Steps 1-5: clone the device template, add macros, and
create the packet loss script item + dependent items + trigger.
"""

from api import api_call, clone_template, add_macros
from config import SOURCE_TEMPLATE, CLONE_TEMPLATE, DEVICE_MACROS, TRIGGER_DESCRIPTION
from scripts import SCRIPT_BODY


def create_script_item(templateid):
    """Create the packet loss Script item on the template, or return its existing id."""
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
    """Create a numeric dependent item that extracts jsonpath from the master item's JSON, or return its existing id."""
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
    """Create the packet loss trigger, or return its existing id."""
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
    """Run the `create` action: clone the device template and add the packet loss item, dependent items, and trigger."""
    templateid = clone_template(SOURCE_TEMPLATE, CLONE_TEMPLATE)
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
