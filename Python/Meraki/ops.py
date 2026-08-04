"""`test`, `rollout`, and `rollback` actions.

test     -> Step 6: force-run the packet loss item on one real host and
            print the raw JSON, without ever re-typing the API token
rollout  -> Step 7B: repoint the device-discovery host prototype at the
            clone and force an immediate re-sync (fleet-wide, deliberate)
rollback -> undoes rollout
"""

import time

from api import api_call, get_template_id, get_host_id
from config import ORG_HOST, TEST_HOST, DISCOVERY_RULE_NAME, SOURCE_TEMPLATE, CLONE_TEMPLATE, DASHBOARD_TEMPLATE


def test_item():
    if not TEST_HOST:
        raise RuntimeError("Set ZABBIX_TEST_HOST to a host with the clone template already attached")

    hostid = get_host_id(TEST_HOST)
    if not hostid:
        raise RuntimeError(f"Host not found: {TEST_HOST}")

    item = api_call(
        "item.get",
        {
            "hostids": [hostid],
            "filter": {"key_": "meraki.get.packetloss"},
            "output": ["itemid", "history"],
        },
    )
    if not item:
        raise RuntimeError(f"Item not found on {TEST_HOST} — attach the clone template first")
    itemid, original_history = item[0]["itemid"], item[0]["history"]

    api_call("item.update", {"itemid": itemid, "history": "1h"})
    api_call("task.create", {"type": 6, "request": {"itemid": itemid}})  # ZBX_TM_TASK_CHECK_NOW
    print("Check-now queued, waiting for a result...")
    time.sleep(5)

    history = api_call(
        "history.get",
        {
            "itemids": [itemid],
            "history": 4,
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": 1,
        },
    )
    if history:
        print("Latest raw value:")
        print(history[0]["value"])
    else:
        print("No history yet — wait a bit and query history.get again before reverting.")

    api_call("item.update", {"itemid": itemid, "history": original_history})
    print(f"History reverted to '{original_history}'.")


def _discovery_rule_itemid(templateid):
    rules = api_call(
        "discoveryrule.get",
        {
            "templateids": [templateid],
            "filter": {"name": [DISCOVERY_RULE_NAME]},
            "output": ["itemid"],
        },
    )
    if not rules:
        raise RuntimeError(f"Discovery rule '{DISCOVERY_RULE_NAME}' not found")
    return rules[0]["itemid"]


def _relink_prototype(new_templateid):
    dash_id = get_template_id(DASHBOARD_TEMPLATE)
    druleid = _discovery_rule_itemid(dash_id)
    prototypes = api_call("hostprototype.get", {"discoveryids": [druleid], "output": ["hostid", "host"]})
    if not prototypes:
        raise RuntimeError("No host prototype found on that discovery rule")
    proto = prototypes[0]
    api_call("hostprototype.update", {"hostid": proto["hostid"], "templates": [{"templateid": new_templateid}]})
    print(f"Host prototype '{proto['host']}' now links to templateid {new_templateid}.")


def _resync_org_host():
    if not ORG_HOST:
        print("Set ZABBIX_ORG_HOST and re-run to also force an immediate re-sync.")
        return
    org_hostid = get_host_id(ORG_HOST)
    if not org_hostid:
        print(f"Org host '{ORG_HOST}' not found — re-sync it manually.")
        return
    org_rules = api_call(
        "discoveryrule.get",
        {
            "hostids": [org_hostid],
            "filter": {"name": [DISCOVERY_RULE_NAME]},
            "output": ["itemid"],
        },
    )
    if not org_rules:
        print("Discovery rule instance not found on org host — re-sync it manually.")
        return
    api_call("task.create", {"type": 6, "request": {"itemid": org_rules[0]["itemid"]}})
    print("Re-sync task queued — check Data collection > Hosts > Discovery shortly.")


def rollout():
    """Step 7B — fleet-wide. Repoints every discovered host, run deliberately."""
    cloneid = get_template_id(CLONE_TEMPLATE)
    _relink_prototype(cloneid)
    _resync_org_host()


def rollback():
    src_id = get_template_id(SOURCE_TEMPLATE)
    _relink_prototype(src_id)
    _resync_org_host()
