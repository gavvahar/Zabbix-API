var params = JSON.parse(value);

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
