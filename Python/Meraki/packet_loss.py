#!/usr/bin/env python3
"""
Provision Meraki wireless monitoring in Zabbix via the API.

Automates instructions.md plus the wireless-health follow-up list end to end:
  create      -> Steps 1-5: clone the device template, add macros, create the
                 packet loss script item + dependent items + trigger
  ap-health   -> extends the device clone: device status poll, AP Down,
                 Firmware Outdated, High Latency, API Failure
  wireless    -> clones the dashboard template and adds Network/SSID/Radio
                 Discovery plus their trigger prototypes (High Client Count,
                 Authentication Failure Rate, Wireless Health Degraded)
  test        -> Step 6: force-run the packet loss item on one real host and
                 print the raw JSON, without ever re-typing the API token
  rollout     -> Step 7B: repoint the device-discovery host prototype at the
                 clone and force an immediate re-sync (fleet-wide, deliberate)
  rollback    -> undoes rollout

Requires Zabbix 6.4+ (Script item type, item-level timeout override,
task.create check-now). Requires `requests` (pip install requests) and a
Zabbix API token (Users > API tokens) with read/write on the relevant hosts.

Environment variables:
  ZABBIX_URL          e.g. https://zabbix.example.com
  ZABBIX_API_TOKEN    API token (Bearer)
  ZABBIX_ORG_HOST     org-level Meraki host name (needed for `rollout`)
  ZABBIX_TEST_HOST    a host with the clone already attached (needed for `test`)

NOT built here — "AP Discovery" from the follow-up list:
The official dashboard template already discovers one host per device via
its "Get data: Devices discovery" LLD rule (see DISCOVERY_RULE_NAME below).
A second discovery rule that also creates per-AP hosts would collide with
those (duplicate host errors). AP-level metrics (status, firmware, latency)
are instead added as static items on the device template clone — same
pattern as the existing packet loss item — since every discovered host
already carries {$SERIAL}. See ap-health / create_ap_health().

Meraki endpoint/field names below (devices/statuses, wireless/ssids,
wireless/failedConnections, wireless/devices/channelUtilization/byDevice)
are best-effort from the public Dashboard API v1 and were NOT verified
against a live org — check field names/response shape against current
Meraki docs before running against production. Thresholds are placeholder
macros (add_macros / DASHBOARD_MACROS) — tune per your environment.
"""

import json, os, sys, time, requests


ZABBIX_URL = os.environ["ZABBIX_URL"].rstrip("/") + "/api_jsonrpc.php"
ZABBIX_TOKEN = os.environ["ZABBIX_API_TOKEN"]
ORG_HOST = os.environ.get("ZABBIX_ORG_HOST", "").strip()
TEST_HOST = os.environ.get("ZABBIX_TEST_HOST", "").strip()

SOURCE_TEMPLATE = "Cisco Meraki device by HTTP"
CLONE_TEMPLATE = "Cisco Meraki device by HTTP - Packet Loss"
DASHBOARD_TEMPLATE = "Cisco Meraki dashboard by HTTP"
DASHBOARD_CLONE_TEMPLATE = "Cisco Meraki dashboard by HTTP - Wireless Health"
DISCOVERY_RULE_NAME = "Get data: Devices discovery"

# {$MERAKI.ORG.ID} is assumed to already exist on the dashboard template
# (org-scoped calls need it) — reuse it, same as {$MERAKI.API.URL} / {$MERAKI.TOKEN}.
DEVICE_MACROS = {
    "{$MERAKI.PING.COUNT}": "5",
    "{$MERAKI.PING.INTERVAL}": "5m",
    "{$MERAKI.PING.TARGET}": "8.8.8.8",
    "{$MERAKI.PING.LOSS}": "20",
    "{$MERAKI.PING.LATENCY.HIGH}": "100",  # ms
    "{$MERAKI.DEVICESTATUS.INTERVAL}": "5m",
    "{$MERAKI.FIRMWARE.EXPECTED}": "",  # blank = Firmware Outdated trigger stays inactive until set
}

DASHBOARD_MACROS = {
    "{$MERAKI.LLD.INTERVAL}": "1h",
    "{$MERAKI.CLIENTCOUNT.HIGH}": "50",
    "{$MERAKI.AUTHFAIL.HIGH}": "20",
    "{$MERAKI.AUTHFAIL.SSID.HIGH}": "10",
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


def add_macros(templateid, macros):
    existing = {m["macro"] for m in api_call("usermacro.get", {"hostids": [templateid], "output": ["macro"]})}
    for macro, value in macros.items():
        if macro in existing:
            continue
        print(f"Adding macro {macro}")
        api_call("usermacro.create", {"hostid": templateid, "macro": macro, "value": value})


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


# ---------------------------------------------------------------------------
# ap-health: device status poll + AP Down / Firmware Outdated / High Latency /
# API Failure, added as static items on the device template clone (see the
# "NOT built here" note at the top for why this isn't a separate LLD rule).
# ---------------------------------------------------------------------------

DEVICE_STATUS_SCRIPT_BODY = r"""
var params = JSON.parse(value);

var request = new HttpRequest();
request.addHeader('X-Cisco-Meraki-API-Key:' + params.token);
request.addHeader('Content-Type: application/json');
request.addHeader('User-Agent: ZabbixServer/1.2 Zabbix');

if (typeof params.httpproxy !== 'undefined' && params.httpproxy !== '') {
  request.setProxy(params.httpproxy);
}

if (params.url.indexOf('http://') === -1 && params.url.indexOf('https://') === -1) {
  params.url = 'https://' + params.url;
}
if (params.url.slice(-1) !== '/') {
  params.url = params.url + '/';
}

var error_msg = '';
var result = {};

try {
  var url = params.url + 'organizations/' + encodeURIComponent(params.orgid) +
    '/devices/statuses?serials%5B%5D=' + encodeURIComponent(params.serial);
  var response = request.get(url);
  var status = request.getStatus();
  var parsed = (response !== null && response !== '') ? JSON.parse(response) : null;

  if (status !== 200) {
    throw (parsed !== null && parsed.errors) ? parsed.errors.join(', ') :
      'Failed to receive data: invalid response status code ' + status + '.';
  }
  if (parsed === null || !parsed.length) {
    throw 'No status entry returned for serial ' + params.serial;
  }
  result = parsed[0];
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
""".strip()


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


# ---------------------------------------------------------------------------
# wireless: clones the dashboard template, adds Network/SSID/Radio Discovery
# (each a self-contained script covering its own API calls, following the
# same flat-LLD pattern as the official "Devices discovery" rule — Zabbix
# doesn't nest discovery rules, so SSID Discovery loops networks internally
# rather than depending on Network Discovery's output).
# ---------------------------------------------------------------------------

_HTTP_SETUP = r"""
var request = new HttpRequest();
request.addHeader('X-Cisco-Meraki-API-Key:' + params.token);
request.addHeader('Content-Type: application/json');
request.addHeader('User-Agent: ZabbixServer/1.2 Zabbix');

if (typeof params.httpproxy !== 'undefined' && params.httpproxy !== '') {
  request.setProxy(params.httpproxy);
}

var url = params.url;
if (url.indexOf('http://') === -1 && url.indexOf('https://') === -1) {
  url = 'https://' + url;
}
if (url.slice(-1) !== '/') {
  url = url + '/';
}
""".strip()

NETWORK_DISCOVERY_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'organizations/' + encodeURIComponent(params.orgid) + '/networks');
if (request.getStatus() !== 200) {
  throw 'Failed to list networks: status ' + request.getStatus();
}

var networks = JSON.parse(response);
var data = [];
networks.forEach(function (net) {
  data.push({
    '{#NETWORK_ID}': net.id,
    '{#NETWORK_NAME}': net.name
  });
});

return JSON.stringify({ data: data });
"""
).strip()

SSID_DISCOVERY_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var netResponse = request.get(url + 'organizations/' + encodeURIComponent(params.orgid) + '/networks');
if (request.getStatus() !== 200) {
  throw 'Failed to list networks: status ' + request.getStatus();
}
var networks = JSON.parse(netResponse);

var data = [];
networks.forEach(function (net) {
  var ssidResponse = request.get(url + 'networks/' + encodeURIComponent(net.id) + '/wireless/ssids');
  if (request.getStatus() !== 200) {
    return; // network has no wireless capability (e.g. appliance-only) — skip it
  }
  var ssids = JSON.parse(ssidResponse);
  ssids.forEach(function (ssid) {
    if (!ssid.enabled) {
      return;
    }
    data.push({
      '{#NETWORK_ID}': net.id,
      '{#NETWORK_NAME}': net.name,
      '{#SSID_NUMBER}': ssid.number,
      '{#SSID_NAME}': ssid.name
    });
  });
});

return JSON.stringify({ data: data });
"""
).strip()

RADIO_DISCOVERY_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'organizations/' + encodeURIComponent(params.orgid) +
  '/wireless/devices/channelUtilization/byDevice?perPage=500');
if (request.getStatus() !== 200) {
  throw 'Failed to list channel utilization: status ' + request.getStatus();
}

var devices = JSON.parse(response);
var data = [];
devices.forEach(function (dev) {
  (dev.byBand || []).forEach(function (band) {
    data.push({
      '{#SERIAL}': dev.serial,
      '{#AP_NAME}': dev.name || dev.serial,
      '{#RADIO_BAND}': band.band
    });
  });
});

return JSON.stringify({ data: data });
"""
).strip()

NETWORK_CLIENTCOUNT_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) + '/clients?timespan=300');
if (request.getStatus() !== 200) {
  throw 'Failed to list clients: status ' + request.getStatus();
}

return JSON.parse(response).length;
"""
).strip()

NETWORK_AUTHFAILURES_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) +
  '/wireless/failedConnections?timespan=3600');
if (request.getStatus() !== 200) {
  throw 'Failed to list failed connections: status ' + request.getStatus();
}

var events = JSON.parse(response);
return events.filter(function (e) { return e.type === 'auth'; }).length;
"""
).strip()

SSID_AUTHFAILURES_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) +
  '/wireless/failedConnections?timespan=3600&ssidNumber=' + encodeURIComponent(params.ssidnumber));
if (request.getStatus() !== 200) {
  throw 'Failed to list failed connections: status ' + request.getStatus();
}

var events = JSON.parse(response);
return events.filter(function (e) { return e.type === 'auth'; }).length;
"""
).strip()

RADIO_UTILIZATION_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var response = request.get(url + 'organizations/' + encodeURIComponent(params.orgid) +
  '/wireless/devices/channelUtilization/byDevice?perPage=500');
if (request.getStatus() !== 200) {
  throw 'Failed to list channel utilization: status ' + request.getStatus();
}

var devices = JSON.parse(response);
var device = null;
for (var i = 0; i < devices.length; i++) {
  if (devices[i].serial === params.serial) {
    device = devices[i];
    break;
  }
}
if (device === null) {
  throw 'No utilization data for ' + params.serial;
}

var band = null;
(device.byBand || []).forEach(function (b) {
  if (b.band === params.band) {
    band = b;
  }
});
if (band === null) {
  throw 'No band data for ' + params.band + ' on ' + params.serial;
}

return band.utilization != null ? band.utilization : 0;
"""
).strip()


def clone_dashboard_template():
    existing = api_call("template.get", {"filter": {"host": [DASHBOARD_CLONE_TEMPLATE]}})
    if existing:
        print(f"'{DASHBOARD_CLONE_TEMPLATE}' already exists, skipping clone.")
        return existing[0]["templateid"]

    print(f"Cloning '{DASHBOARD_TEMPLATE}' -> '{DASHBOARD_CLONE_TEMPLATE}'")
    src_id = get_template_id(DASHBOARD_TEMPLATE)
    exported = api_call("configuration.export", {"format": "json", "options": {"templates": [src_id]}})
    data = json.loads(exported)
    tmpl = data["zabbix_export"]["templates"][0]
    tmpl["template"] = DASHBOARD_CLONE_TEMPLATE
    tmpl["name"] = DASHBOARD_CLONE_TEMPLATE
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
    return get_template_id(DASHBOARD_CLONE_TEMPLATE)


def create_discovery_rule(templateid, name, key, script_body, parameters, lifetime="7d"):
    found = api_call("discoveryrule.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating discovery rule '{name}'")
    result = api_call(
        "discoveryrule.create",
        {
            "hostid": templateid,
            "name": name,
            "key_": key,
            "type": 21,  # Script
            "delay": "{$MERAKI.LLD.INTERVAL}",
            "timeout": "{$MERAKI.DATA.TIMEOUT}",
            "lifetime": lifetime,
            "params": script_body,
            "parameters": parameters,
        },
    )
    return result["itemids"][0]


def create_itemprototype(templateid, ruleid, name, key, script_body, parameters, value_type=3, units=None):
    found = api_call("itemprototype.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating item prototype '{name}'")
    payload = {
        "hostid": templateid,
        "ruleid": ruleid,
        "name": name,
        "key_": key,
        "type": 21,  # Script
        "value_type": value_type,  # 3 = Numeric unsigned
        "delay": "{$MERAKI.LLD.INTERVAL}",
        "timeout": "{$MERAKI.DATA.TIMEOUT}",
        "history": "31d",
        "params": script_body,
        "parameters": parameters,
    }
    if units:
        payload["units"] = units
    result = api_call("itemprototype.create", payload)
    return result["itemids"][0]


def create_trigger_prototype(templateid, description, expression, priority, tag_value="performance"):
    found = api_call("triggerprototype.get", {"hostids": [templateid], "filter": {"description": description}})
    if found:
        return found[0]["triggerid"]

    print(f"Creating trigger prototype '{description}'")
    result = api_call(
        "triggerprototype.create",
        {
            "description": description,
            "expression": expression,
            "priority": priority,
            "tags": [{"tag": "scope", "value": tag_value}],
        },
    )
    return result["triggerids"][0]


def create_wireless_health():
    templateid = clone_dashboard_template()
    add_macros(templateid, DASHBOARD_MACROS)

    api_params = [
        {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
        {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
        {"name": "token", "value": "{$MERAKI.TOKEN}"},
        {"name": "url", "value": "{$MERAKI.API.URL}"},
    ]

    # --- Network Discovery: client count + auth failures per network ---
    network_ruleid = create_discovery_rule(
        templateid,
        "Network Discovery",
        "meraki.lld.networks",
        NETWORK_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    clientcount_key = "meraki.network.clientcount[{#NETWORK_ID}]"
    create_itemprototype(
        templateid,
        network_ruleid,
        "Client count: {#NETWORK_NAME}",
        clientcount_key,
        NETWORK_CLIENTCOUNT_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
    )
    net_authfail_key = "meraki.network.authfailures[{#NETWORK_ID}]"
    create_itemprototype(
        templateid,
        network_ruleid,
        "Auth failures (1h): {#NETWORK_NAME}",
        net_authfail_key,
        NETWORK_AUTHFAILURES_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
    )
    create_trigger_prototype(
        templateid,
        "Meraki: High client count on {#NETWORK_NAME}",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{clientcount_key})>{{$MERAKI.CLIENTCOUNT.HIGH}}",
        2,  # Warning
    )
    # Degraded = elevated network-wide auth failures, or client count well past the "high" watermark.
    # Deliberately doesn't fold in latency/packet loss — those live on the per-device template, a
    # different discovery rule's scope, and Zabbix trigger prototypes can't mix LLD contexts.
    create_trigger_prototype(
        templateid,
        "Meraki: Wireless health degraded on {#NETWORK_NAME}",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{net_authfail_key})>{{$MERAKI.AUTHFAIL.HIGH}} or last(/{DASHBOARD_CLONE_TEMPLATE}/{clientcount_key})>({{$MERAKI.CLIENTCOUNT.HIGH}}*2)",
        3,  # Average
    )

    # --- SSID Discovery: per-SSID auth failures ---
    ssid_ruleid = create_discovery_rule(
        templateid,
        "SSID Discovery",
        "meraki.lld.ssids",
        SSID_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    ssid_authfail_key = "meraki.ssid.authfailures[{#NETWORK_ID},{#SSID_NUMBER}]"
    create_itemprototype(
        templateid,
        ssid_ruleid,
        "Auth failures (1h): {#SSID_NAME} on {#NETWORK_NAME}",
        ssid_authfail_key,
        SSID_AUTHFAILURES_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "ssidnumber", "value": "{#SSID_NUMBER}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
    )
    create_trigger_prototype(
        templateid,
        "Meraki: Authentication failure rate high on {#SSID_NAME} ({#NETWORK_NAME})",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{ssid_authfail_key})>{{$MERAKI.AUTHFAIL.SSID.HIGH}}",
        2,  # Warning
    )

    # --- Radio Discovery: per-AP, per-band channel utilization (data only — not in the trigger list) ---
    radio_ruleid = create_discovery_rule(
        templateid,
        "Radio Discovery",
        "meraki.lld.radios",
        RADIO_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    create_itemprototype(
        templateid,
        radio_ruleid,
        "Channel utilization: {#AP_NAME} ({#RADIO_BAND}GHz)",
        "meraki.radio.utilization[{#SERIAL},{#RADIO_BAND}]",
        RADIO_UTILIZATION_SCRIPT_BODY,
        [
            {"name": "band", "value": "{#RADIO_BAND}"},
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
            {"name": "serial", "value": "{#SERIAL}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        value_type=0,
        units="%",  # Numeric float
    )

    print(f"Done. '{DASHBOARD_CLONE_TEMPLATE}' is ready (templateid {templateid}).")
    print("This only builds the template — it does not touch any live host.")
    print(f"Attach it to your org host yourself (replacing '{DASHBOARD_TEMPLATE}') to activate the LLD rules.")


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


def main_ap_health():
    templateid = get_template_id(CLONE_TEMPLATE)
    create_ap_health(templateid)
    print(f"Done. AP health items/triggers added to '{CLONE_TEMPLATE}'.")


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


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    {
        "create": main,
        "ap-health": main_ap_health,
        "wireless": create_wireless_health,
        "test": test_item,
        "rollout": rollout,
        "rollback": rollback,
    }.get(
        action,
        lambda: print("Usage: python zabbix_meraki_packetloss.py [create|ap-health|wireless|test|rollout|rollback]"),
    )()
