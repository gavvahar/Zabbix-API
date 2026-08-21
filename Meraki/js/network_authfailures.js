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

var response = request.get(
  url +
    "networks/" +
    encodeURIComponent(params.networkid) +
    "/wireless/failedConnections?timespan=3600"
);
if (request.getStatus() !== 200) {
  throw "Failed to list failed connections: status " + request.getStatus();
}

var events = JSON.parse(response);
return events.filter(function (e) {
  return e.type === "auth";
}).length;
