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
