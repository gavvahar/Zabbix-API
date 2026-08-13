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
    "/clients?timespan=300",
);
if (request.getStatus() !== 200) {
  throw "Failed to list clients: status " + request.getStatus();
}

var clients = JSON.parse(response);
var count = 0;
clients.forEach(function (c) {
  if (c.ssid === params.ssidname) {
    count++;
  }
});
return count;
