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

// Deliberately its own poller rather than sharing meraki.device.get.status's
// master item — that item may be the official template's own poller (reused
// by resolve_device_status_item() to avoid a redundant one), whose JSON shape
// is narrower and isn't ours to assume. This calls devices/statuses directly
// so the full shape (publicIp, lastReportedAt, productType) is guaranteed.
try {
  var statusUrl = params.url + 'organizations/' + encodeURIComponent(params.orgid) +
    '/devices/statuses?serials%5B%5D=' + encodeURIComponent(params.serial);
  var t0 = Date.now();
  var statusResp = request.get(statusUrl);
  var responseTimeMs = Date.now() - t0;
  if (request.getStatus() !== 200) {
    throw 'Failed to get device status: status ' + request.getStatus();
  }
  var statusList = JSON.parse(statusResp);
  if (!statusList.length) {
    throw 'No status entry returned for serial ' + params.serial;
  }
  var device = statusList[0];

  var networkName = '';
  if (device.networkId) {
    var netResp = request.get(params.url + 'networks/' + encodeURIComponent(device.networkId));
    if (request.getStatus() === 200) {
      networkName = JSON.parse(netResp).name || '';
    }
  }

  var orgName = '';
  var orgResp = request.get(params.url + 'organizations/' + encodeURIComponent(params.orgid));
  if (request.getStatus() === 200) {
    orgName = JSON.parse(orgResp).name || '';
  }

  result = {
    publicIp: device.publicIp || '',
    lastReportedAtUnix: device.lastReportedAt ? Math.floor(new Date(device.lastReportedAt).getTime() / 1000) : 0,
    productType: device.productType || '',
    networkName: networkName,
    organizationName: orgName,
    tags: (device.tags || []).join(', '),
    apiResponseTimeMs: responseTimeMs,
    lastSuccessfulPollUnix: Math.floor(Date.now() / 1000)
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
