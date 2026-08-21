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
      "/groupPolicies/" +
      encodeURIComponent(params.grouppolicyid)
  );
  if (request.getStatus() !== 200) {
    throw "Failed to get group policy: status " + request.getStatus();
  }
  var gp = JSON.parse(response);
  var limits =
    gp.bandwidth && gp.bandwidth.bandwidthLimits
      ? gp.bandwidth.bandwidthLimits
      : {};
  result = {
    limitUpKbps: limits.limitUp != null ? limits.limitUp : 0,
    limitDownKbps: limits.limitDown != null ? limits.limitDown : 0,
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  result: result,
  error: error_msg,
});
