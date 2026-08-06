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
  var response = request.get(url + 'networks/' + encodeURIComponent(params.networkid) + '/clients?timespan=300');
  if (request.getStatus() !== 200) {
    throw 'Failed to list clients: status ' + request.getStatus();
  }
  var clients = JSON.parse(response);
  var sentKB = 0;
  var recvKB = 0;
  clients.forEach(function (c) {
    if (c.usage) {
      sentKB += c.usage.sent || 0;
      recvKB += c.usage.recv || 0;
    }
  });
  var timespanSeconds = 300;
  result = {
    sentKbps: (sentKB * 8) / timespanSeconds,
    receivedKbps: (recvKB * 8) / timespanSeconds,
    totalKbps: ((sentKB + recvKB) * 8) / timespanSeconds
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  'result': result,
  'error': error_msg
});
