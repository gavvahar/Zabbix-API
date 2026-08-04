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

# The official "Cisco Meraki device by HTTP" template already ships its own
# device status poller + error mirror under these keys. When a clone still
# carries them (as opposed to a from-scratch or modified clone), reuse them
# instead of adding a second, redundant poller — but only when they're
# actually present; templates without them fall back to the dedicated
# poller below.
OFFICIAL_STATUS_ITEM_KEY = "meraki.device.get.status"
OFFICIAL_STATUS_ERRORS_KEY = "meraki.device.get.status.errors"


def _find_item_by_key(templateid, key):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": key}, "output": ["itemid"]})
    return found[0]["itemid"] if found else None


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


def resolve_device_status_item(templateid):
    """Prefer reusing an already-present device status poller over creating
    a redundant one.

    Preference order: our own ap-health poller (if a previous run already
    created it) > the official template's own status poller + error mirror,
    if this clone still carries them > a brand new ap-health-specific
    poller, as a fallback for templates that have neither.

    Returns (status_itemid, status_error_key). status_error_key is the item
    key to use for the "API failure" trigger's status-error check, or None
    when reusing the official poller without a known error mirror to point
    at — its JSON shape isn't ours to assume, so we don't guess a JSONPath.
    """
    existing = _find_item_by_key(templateid, "meraki.get.devicestatus")
    if existing:
        return existing, "meraki.device.status.error"

    official_status_itemid = _find_item_by_key(templateid, OFFICIAL_STATUS_ITEM_KEY)
    if official_status_itemid:
        print(f"Found existing '{OFFICIAL_STATUS_ITEM_KEY}' item — reusing it instead of creating a duplicate device status poller.")
        official_errors_itemid = _find_item_by_key(templateid, OFFICIAL_STATUS_ERRORS_KEY)
        status_error_key = OFFICIAL_STATUS_ERRORS_KEY if official_errors_itemid else None
        return official_status_itemid, status_error_key

    return create_device_status_item(templateid), "meraki.device.status.error"


def create_ap_health(templateid):
    status_itemid, status_error_key = resolve_device_status_item(templateid)
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
    # Error mirror, kept even when empty (discard_on_fail=False) so "no error" is a real value,
    # not a gap — API Failure below needs to see it either way. Only added when we control the
    # poller's JSON shape (our own {result, error} envelope) — when reusing the official item's
    # own error mirror instead (or none is available), skip adding a redundant one.
    if status_error_key == "meraki.device.status.error":
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

    api_failure_conditions = [f"length(last(/{CLONE_TEMPLATE}/meraki.get.packetloss.error))>0"]
    if status_error_key:
        api_failure_conditions.insert(0, f"length(last(/{CLONE_TEMPLATE}/{status_error_key}))>0")

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
            " or ".join(api_failure_conditions),
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
