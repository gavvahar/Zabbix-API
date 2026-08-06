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

var error_msg = '';
var result = {};

try {
  var response = request.get(url + 'organizations/' + encodeURIComponent(params.orgid) +
    '/wireless/ssids/statuses/byDevice?serials%5B%5D=' + encodeURIComponent(params.serial));
  if (request.getStatus() !== 200) {
    throw 'Failed to get radio status: status ' + request.getStatus();
  }
  var parsed = JSON.parse(response);
  var device = (parsed.items || [])[0];
  var radios = {};
  if (device) {
    (device.basicServiceSets || []).forEach(function (bss) {
      if (!bss.radio) {
        return;
      }
      var key = bss.radio.band + '_' + bss.radio.index;
      if (!radios[key]) {
        radios[key] = {
          channel: bss.radio.channel,
          channelWidth: bss.radio.channelWidth,
          power: bss.radio.power,
          broadcasting: false,
          ssidNames: []
        };
      }
      if (bss.radio.isBroadcasting) {
        radios[key].broadcasting = true;
        if (bss.ssid && bss.ssid.name) {
          radios[key].ssidNames.push(bss.ssid.name);
        }
      }
    });
  }
  Object.keys(radios).forEach(function (key) {
    radios[key].ssids = radios[key].ssidNames.join(', ');
    delete radios[key].ssidNames;
  });
  result = { radios: radios };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
