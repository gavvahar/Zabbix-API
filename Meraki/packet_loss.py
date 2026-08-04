#!/usr/bin/env python3
"""
Provision Meraki Live-Tools-Ping packet loss monitoring in Zabbix via the API.

Automates instructions.md end to end:
  create   -> Steps 1-5: clone the device template, add macros, create the
              script item + two dependent items + trigger
  test     -> Step 6: force-run the item on one real host and print the raw
              JSON, without ever re-typing the API token
  rollout  -> Step 7B: repoint the device-discovery host prototype at the
              clone and force an immediate re-sync (fleet-wide, run deliberately)
  rollback -> undoes rollout

Requires Zabbix 6.4+ (Script item type, item-level timeout override,
task.create check-now). Requires `requests` (pip install requests) and a
Zabbix API token (Users > API tokens) with read/write on the relevant hosts.

Environment variables:
  ZABBIX_URL          e.g. https://zabbix.example.com
  ZABBIX_API_TOKEN    API token (Bearer)
  ZABBIX_ORG_HOST     org-level Meraki host name (needed for `rollout`)
  ZABBIX_TEST_HOST    a host with the clone already attached (needed for `test`)
"""

import json
import os
import sys
import time

import requests

ZABBIX_URL = os.environ["ZABBIX_URL"].rstrip("/") + "/api_jsonrpc.php"
ZABBIX_TOKEN = os.environ["ZABBIX_API_TOKEN"]
ORG_HOST = os.environ.get("ZABBIX_ORG_HOST", "").strip()
TEST_HOST = os.environ.get("ZABBIX_TEST_HOST", "").strip()

SOURCE_TEMPLATE = "Cisco Meraki device by HTTP"
CLONE_TEMPLATE = "Cisco Meraki device by HTTP - Packet Loss"
DASHBOARD_TEMPLATE = "Cisco Meraki dashboard by HTTP"
DISCOVERY_RULE_NAME = "Get data: Devices discovery"

MACROS = {
    "{$MERAKI.PING.COUNT}": "5",
    "{$MERAKI.PING.INTERVAL}": "5m",
    "{$MERAKI.PING.TARGET}": "8.8.8.8",
    "{$MERAKI.PING.LOSS}": "20",
}

TRIGGER_DESCRIPTION = "Meraki: Packet loss to {$MERAKI.PING.TARGET} > {$MERAKI.PING.LOSS}%"

# Reconstructed clean from instructions.md (stray ``` markers in that doc's
# code block were formatting artifacts and would break the script as-is).
SCRIPT_BODY = r"""
var params = JSON.parse(value);

var request = new HttpRequest();
request.addHeader('X-Cisco-Meraki-API-Key:' + params.token);
request.addHeader('Content-Type: application/json');
request.addHeader('User-Agent: ZabbixServer/1.2 Zabbix');

if (typeof params.httpproxy !== 'undefined' && params.httpproxy !== '') {
  request.setProxy(params.httpproxy);
}

if (params.token === '{' + 'MERAKI.TOKEN}') {
  throw 'Please change {MERAKI.TOKEN} macro to the proper value.';
}

if (params.url.indexOf('http://') === -1 && params.url.indexOf('https://') === -1) {
  params.url = 'https://' + params.url;
}
if (params.url.slice(-1) !== '/') {
  params.url = params.url + '/';
}

var error_msg = '';
var result = {};

function getHttpData(method, url, body) {
  var response;
  if (method === 'POST') {
    response = request.post(url, JSON.stringify(body));
  } else {
    response = request.get(url);
  }
  var status = request.getStatus();
  Zabbix.log(4, '[ Meraki API ] [ ' + url + ' ] Received response with status code ' + status + ': ' + response);

  var parsed = null;
  if (response !== null && response !== '') {
    parsed = JSON.parse(response);
  }
  if (status !== 200 && status !== 201) {
    if (parsed !== null && parsed.errors) {
      throw parsed.errors.join(', ');
    }
    throw 'Failed to receive data: invalid response status code ' + status + '.';
  }
  return parsed === null ? {} : parsed;
}

try {
  var createBody = {
    count: parseInt(params.count, 10) || 5,
    target: params.target
  };

  var baseUrl = params.url + 'devices/' + encodeURIComponent(params.serial) + '/liveTools/ping';
  var createResp = getHttpData('POST', baseUrl, createBody);

  if (!createResp.pingId) {
    throw 'Failed to create ping job: no pingId returned.';
  }

  var pollUrl = baseUrl + '/' + createResp.pingId;
  var maxAttempts = 15;
  var attempt = 0;

  while (attempt < maxAttempts) {
    Zabbix.sleep(2000);
    result = getHttpData('GET', pollUrl, null);
    if (result.status === 'complete' || result.status === 'failed') {
      break;
    }
    attempt++;
  }

  if (result.status !== 'complete') {
    throw 'Ping test did not complete in time. Last status: ' + result.status;
  }
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
""".strip()


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


def add_macros(templateid):
    existing = {m["macro"] for m in api_call("usermacro.get", {"hostids": [templateid], "output": ["macro"]})}
    for macro, value in MACROS.items():
        if macro in existing:
            continue
        print(f"Adding macro {macro}")
        api_call("usermacro.create", {"hostid": templateid, "macro": macro, "value": value})


def create_script_item(templateid):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": "meraki.get.packetloss"}})
    if found:
        return found[0]["itemid"]

    print("Creating 'Get packet loss data' script item")
    result = api_call("item.create", {
        "hostid": templateid,
        "name": "Get packet loss data",
        "key_": "meraki.get.packetloss",
        "type": 21,       # Script
        "value_type": 4,  # Text
        "delay": "{$MERAKI.PING.INTERVAL};50s/1-7,00:00-24:00",
        "timeout": "{$MERAKI.DATA.TIMEOUT}",
        "history": "0",   # Do not store
        "params": SCRIPT_BODY,
        "parameters": [
            {"name": "count", "value": "{$MERAKI.PING.COUNT}"},
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "serial", "value": "{$SERIAL}"},
            {"name": "target", "value": "{$MERAKI.PING.TARGET}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
    })
    return result["itemids"][0]


def create_dependent_item(templateid, master_itemid, name, key, jsonpath, units):
    found = api_call("item.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating dependent item '{name}'")
    result = api_call("item.create", {
        "hostid": templateid,
        "name": name,
        "key_": key,
        "type": 18,  # Dependent item
        "master_itemid": master_itemid,
        "value_type": 0,  # Numeric float
        "units": units,
        "history": "31d",
        "trends": "365d",
        "preprocessing": [{
            "type": 12,  # JSONPath
            "params": jsonpath,
            "error_handler": 1,  # Discard value
            "error_handler_params": "",
        }],
    })
    return result["itemids"][0]


def create_trigger(templateid):
    found = api_call("trigger.get", {"hostids": [templateid], "filter": {"description": TRIGGER_DESCRIPTION}})
    if found:
        return found[0]["triggerid"]

    print("Creating packet loss trigger")
    expression = f"min(/{CLONE_TEMPLATE}/meraki.device.packetloss.pct,#3)>{{$MERAKI.PING.LOSS}}"
    result = api_call("trigger.create", {
        "description": TRIGGER_DESCRIPTION,
        "expression": expression,
        "priority": 2,  # Warning
        "tags": [{"tag": "scope", "value": "performance"}],
    })
    return result["triggerids"][0]


def main():
    templateid = clone_template()
    add_macros(templateid)
    script_itemid = create_script_item(templateid)
    create_dependent_item(
        templateid, script_itemid, "Latency, ms", "meraki.device.ping.latency",
        "$.result.results.latencies.average", "ms",
    )
    create_dependent_item(
        templateid, script_itemid, "Packet loss, %", "meraki.device.packetloss.pct",
        "$.result.results.loss.percentage", "%",
    )
    create_trigger(templateid)
    print(f"Done. '{CLONE_TEMPLATE}' is ready (templateid {templateid}).")
    print("Next: attach it to a test host and run `test`, then `rollout` when ready.")


def test_item():
    if not TEST_HOST:
        raise RuntimeError("Set ZABBIX_TEST_HOST to a host with the clone template already attached")

    hostid = get_host_id(TEST_HOST)
    if not hostid:
        raise RuntimeError(f"Host not found: {TEST_HOST}")

    item = api_call("item.get", {
        "hostids": [hostid],
        "filter": {"key_": "meraki.get.packetloss"},
        "output": ["itemid", "history"],
    })
    if not item:
        raise RuntimeError(f"Item not found on {TEST_HOST} — attach the clone template first")
    itemid, original_history = item[0]["itemid"], item[0]["history"]

    api_call("item.update", {"itemid": itemid, "history": "1h"})
    api_call("task.create", {"type": 6, "request": {"itemid": itemid}})  # ZBX_TM_TASK_CHECK_NOW
    print("Check-now queued, waiting for a result...")
    time.sleep(5)

    history = api_call("history.get", {
        "itemids": [itemid], "history": 4, "sortfield": "clock", "sortorder": "DESC", "limit": 1,
    })
    if history:
        print("Latest raw value:")
        print(history[0]["value"])
    else:
        print("No history yet — wait a bit and query history.get again before reverting.")

    api_call("item.update", {"itemid": itemid, "history": original_history})
    print(f"History reverted to '{original_history}'.")


def _discovery_rule_itemid(templateid):
    rules = api_call("discoveryrule.get", {
        "templateids": [templateid], "filter": {"name": [DISCOVERY_RULE_NAME]}, "output": ["itemid"],
    })
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
    org_rules = api_call("discoveryrule.get", {
        "hostids": [org_hostid], "filter": {"name": [DISCOVERY_RULE_NAME]}, "output": ["itemid"],
    })
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


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    {
        "create": main,
        "test": test_item,
        "rollout": rollout,
        "rollback": rollback,
    }.get(action, lambda: print("Usage: python zabbix_meraki_packetloss.py [create|test|rollout|rollback]"))()
