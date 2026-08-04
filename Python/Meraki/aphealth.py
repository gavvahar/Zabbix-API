"""`ap-health` action — extends the device clone: device status poll, AP Down,
Firmware Outdated, High Latency, API Failure.

NOT built here — "AP Discovery" from the follow-up list:
The official dashboard template already discovers one host per device via
its "Get data: Devices discovery" LLD rule. A second discovery rule that
also creates per-AP hosts would collide with those (duplicate host errors).
AP-level metrics (status, firmware, latency) are instead added as static
items on the device template clone — same pattern as the existing packet
loss item — since every discovered host already carries {$SERIAL}.
"""

from api import api_call, get_template_id
from config import CLONE_TEMPLATE
from scripts import DEVICE_STATUS_SCRIPT_BODY


def create_device_status_item(templateid):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": "meraki.get.devicestatus"}})
    if found:
        return found[0]["itemid"]

    print("Creating 'Get device status' script item")
    result = api_call(
        "item.create",
        {
            "hostid": templateid,
            "name": "Get device status",
            "key_": "meraki.get.devicestatus",
            "type": 21,  # Script
            "value_type": 4,  # Text
            "delay": "{$MERAKI.DEVICESTATUS.INTERVAL}",
            "timeout": "{$MERAKI.DATA.TIMEOUT}",
            "history": "0",  # Do not store — raw JSON, mirrored by dependent items below
            "params": DEVICE_STATUS_SCRIPT_BODY,
            "parameters": [
                {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
                {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
                {"name": "serial", "value": "{$SERIAL}"},
                {"name": "token", "value": "{$MERAKI.TOKEN}"},
                {"name": "url", "value": "{$MERAKI.API.URL}"},
            ],
        },
    )
    return result["itemids"][0]


def create_text_dependent_item(templateid, master_itemid, name, key, jsonpath, discard_on_fail=True):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating dependent item '{name}'")
    preprocessing = [
        {
            "type": 12,  # JSONPath
            "params": jsonpath,
            "error_handler": 1 if discard_on_fail else 0,
            "error_handler_params": "",
        }
    ]
    result = api_call(
        "item.create",
        {
            "hostid": templateid,
            "name": name,
            "key_": key,
            "type": 18,  # Dependent item
            "master_itemid": master_itemid,
            "value_type": 4,  # Text
            "history": "31d",
            "preprocessing": preprocessing,
        },
    )
    return result["itemids"][0]


def create_ap_health(templateid):
    status_itemid = create_device_status_item(templateid)
    packetloss_itemid = api_call(
        "item.get",
        {
            "hostids": [templateid],
            "filter": {"key_": "meraki.get.packetloss"},
            "output": ["itemid"],
        },
    )[0]["itemid"]

    create_text_dependent_item(
        templateid,
        status_itemid,
        "Device status",
        "meraki.device.status",
        "$.result.status",
    )
    create_text_dependent_item(
        templateid,
        status_itemid,
        "Firmware version",
        "meraki.device.firmware",
        "$.result.firmware",
    )
    # Error mirrors, kept even when empty (discard_on_fail=False) so "no error" is a real value,
    # not a gap — API Failure below needs to see it either way.
    create_text_dependent_item(
        templateid,
        status_itemid,
        "Device status: API error",
        "meraki.device.status.error",
        "$.error",
        discard_on_fail=False,
    )
    create_text_dependent_item(
        templateid,
        packetloss_itemid,
        "Packet loss: API error",
        "meraki.get.packetloss.error",
        "$.error",
        discard_on_fail=False,
    )

    triggers = [
        (
            "Meraki: AP {HOST.NAME} is down",
            f'last(/{CLONE_TEMPLATE}/meraki.device.status)="offline"',
            4,  # High
        ),
        (
            "Meraki: {HOST.NAME} firmware outdated (expected {$MERAKI.FIRMWARE.EXPECTED})",
            f'{{$MERAKI.FIRMWARE.EXPECTED}}<>"" and last(/{CLONE_TEMPLATE}/meraki.device.firmware)<>{{$MERAKI.FIRMWARE.EXPECTED}}',
            1,  # Information
        ),
        (
            "Meraki: High latency to {$MERAKI.PING.TARGET} on {HOST.NAME}",
            f"min(/{CLONE_TEMPLATE}/meraki.device.ping.latency,#3)>{{$MERAKI.PING.LATENCY.HIGH}}",
            2,  # Warning
        ),
        (
            "Meraki: API failure polling {HOST.NAME}",
            f"length(last(/{CLONE_TEMPLATE}/meraki.device.status.error))>0 or length(last(/{CLONE_TEMPLATE}/meraki.get.packetloss.error))>0",
            3,  # Average
        ),
    ]
    for description, expression, priority in triggers:
        found = api_call("trigger.get", {"hostids": [templateid], "filter": {"description": description}})
        if found:
            continue
        print(f"Creating trigger '{description}'")
        api_call(
            "trigger.create",
            {
                "description": description,
                "expression": expression,
                "priority": priority,
                "tags": [{"tag": "scope", "value": "availability"}],
            },
        )


def main_ap_health():
    templateid = get_template_id(CLONE_TEMPLATE)
    create_ap_health(templateid)
    print(f"Done. AP health items/triggers added to '{CLONE_TEMPLATE}'.")
