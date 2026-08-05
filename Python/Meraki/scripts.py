"""Zabbix Script item bodies (plain JavaScript, run by the Zabbix server/proxy).

Meraki endpoint/field names below (devices/statuses, wireless/ssids,
wireless/failedConnections, wireless/devices/channelUtilization/byDevice)
are best-effort from the public Dashboard API v1 and were NOT verified
against a live org — check field names/response shape against current
Meraki docs before running against production.
"""

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
var failures = [];
networks.forEach(function (net) {
  var ssidResponse = request.get(url + 'networks/' + encodeURIComponent(net.id) + '/wireless/ssids');
  var status = request.getStatus();
  if (status !== 200) {
    // Legitimately non-wireless networks (e.g. appliance-only) 404 here — that's
    // fine to skip. But silently swallowing EVERY status code hides real failures
    // (auth/permission errors, wrong path, etc.), so failures are collected and
    // only ignored if at least one network came back with real SSID data.
    failures.push(net.name + ' (' + net.id + '): status ' + status + ' - ' + (ssidResponse || '').substring(0, 200));
    return;
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

if (data.length === 0 && failures.length > 0) {
  throw 'No SSIDs found; per-network failures: ' + failures.join(' | ');
}

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

SSID_CLIENTCOUNT_SCRIPT_BODY = (
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

var clients = JSON.parse(response);
var count = 0;
clients.forEach(function (c) {
  if (c.ssid === params.ssidname) {
    count++;
  }
});
return count;
"""
).strip()

# connectionStats buckets (assoc/auth/dhcp/dns) are each a count of clients that
# FAILED at that funnel step; 'success' is clients that completed the whole
# funnel. successRatePct is computed here (rather than via item preprocessing)
# so only the already-used JSONPath preprocessing type is needed downstream.
NETWORK_CONNECTIONSTATS_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var error_msg = '';
var result = {};

try {
  var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) +
    '/wireless/connectionStats?timespan=3600');
  if (request.getStatus() !== 200) {
    throw 'Failed to get connection stats: status ' + request.getStatus();
  }
  var stats = JSON.parse(response);
  var assoc = stats.assoc || 0;
  var auth = stats.auth || 0;
  var dhcp = stats.dhcp || 0;
  var dns = stats.dns || 0;
  var success = stats.success || 0;
  var total = assoc + auth + dhcp + dns + success;
  result = {
    dhcp: dhcp,
    dns: dns,
    successRatePct: total > 0 ? (success / total * 100) : 0
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
"""
).strip()

SSID_CONNECTIONSTATS_SCRIPT_BODY = (
    r"""
var params = JSON.parse(value);
"""
    + "\n"
    + _HTTP_SETUP
    + r"""

var error_msg = '';
var result = {};

try {
  var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) +
    '/wireless/ssids/' + encodeURIComponent(params.ssidnumber) + '/connectionStats?timespan=3600');
  if (request.getStatus() !== 200) {
    throw 'Failed to get connection stats: status ' + request.getStatus();
  }
  var stats = JSON.parse(response);
  var assoc = stats.assoc || 0;
  var auth = stats.auth || 0;
  var dhcp = stats.dhcp || 0;
  var dns = stats.dns || 0;
  var success = stats.success || 0;
  var total = assoc + auth + dhcp + dns + success;
  result = {
    dhcp: dhcp,
    dns: dns,
    successRatePct: total > 0 ? (success / total * 100) : 0
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
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
