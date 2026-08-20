var params = JSON.parse(value);

var request = new HttpRequest();
request.addHeader("X-Cisco-Meraki-API-Key:" + params.token);
request.addHeader("Content-Type: application/json");
request.addHeader("User-Agent: ZabbixServer/1.2 Zabbix");

if (typeof params.httpproxy !== "undefined" && params.httpproxy !== "") {
  request.setProxy(params.httpproxy);
}

var url = params.url;
if (url.indexOf("http://") === -1 && url.indexOf("https://") === -1) {
  url = "https://" + url;
}
if (url.slice(-1) !== "/") {
  url = url + "/";
}

var error_msg = "";
var result = {};

try {
  var response = request.get(
    url +
      "networks/" +
      encodeURIComponent(params.networkid) +
      "/wireless/ssids/" +
      encodeURIComponent(params.ssidnumber) +
      "/connectionStats?timespan=3600"
  );
  if (request.getStatus() !== 200) {
    throw "Failed to get connection stats: status " + request.getStatus();
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
    successRatePct: total > 0 ? (success / total) * 100 : 0,
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  result: result,
  error: error_msg,
});
