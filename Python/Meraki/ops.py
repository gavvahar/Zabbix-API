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
    """Force-run the packet loss item on ZABBIX_TEST_HOST and print its latest raw value."""
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


def _find_discovery_rule_itemid():
    """Find the devices-discovery rule's itemid.

    Prefers ZABBIX_ORG_HOST's own live instance of the rule, if that host
    var is set and resolvable — this works regardless of whether the org
    host currently carries the official dashboard template or a clone made
    by the `wireless` action, since hostprototype.get accepts either a
    template-level or a host-level (inherited) discovery rule itemid.
    Falls back to the official dashboard template's own copy when
    ZABBIX_ORG_HOST isn't set, matching the original behavior.
    """
    if ORG_HOST:
        org_hostid = get_host_id(ORG_HOST)
        if org_hostid:
            rules = api_call(
                "discoveryrule.get",
                {"hostids": [org_hostid], "filter": {"name": [DISCOVERY_RULE_NAME]}, "output": ["itemid"]},
            )
            if rules:
                return rules[0]["itemid"]

    dash_id = get_template_id(DASHBOARD_TEMPLATE)
    rules = api_call(
        "discoveryrule.get",
        {"templateids": [dash_id], "filter": {"name": [DISCOVERY_RULE_NAME]}, "output": ["itemid"]},
    )
    if not rules:
        raise RuntimeError(f"Discovery rule '{DISCOVERY_RULE_NAME}' not found")
    return rules[0]["itemid"]


def _relink_prototype(new_templateid):
    """Point the device-discovery host prototype's template link at new_templateid."""
    druleid = _find_discovery_rule_itemid()
    prototypes = api_call("hostprototype.get", {"discoveryids": [druleid], "output": ["hostid", "host"]})
    if not prototypes:
        raise RuntimeError("No host prototype found on that discovery rule")
    proto = prototypes[0]
    api_call("hostprototype.update", {"hostid": proto["hostid"], "templates": [{"templateid": new_templateid}]})
    print(f"Host prototype '{proto['host']}' now links to templateid {new_templateid}.")


def _resync_org_host():
    """Force an immediate re-sync of the org host's discovery rule, if ZABBIX_ORG_HOST is set."""
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
    """Undo rollout by repointing the host prototype back at the source template."""
    src_id = get_template_id(SOURCE_TEMPLATE)
    _relink_prototype(src_id)
    _resync_org_host()
