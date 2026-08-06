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

var netResponse = request.get(
  url + "organizations/" + encodeURIComponent(params.orgid) + "/networks",
);
if (request.getStatus() !== 200) {
  throw "Failed to list networks: status " + request.getStatus();
}
var networks = JSON.parse(netResponse);

var data = [];
var failures = [];
networks.forEach(function (net) {
  var ssidResponse = request.get(
    url + "networks/" + encodeURIComponent(net.id) + "/wireless/ssids",
  );
  var status = request.getStatus();
  if (status !== 200) {
    // Legitimately non-wireless networks (e.g. appliance-only) 404 here — that's
    // fine to skip. But silently swallowing EVERY status code hides real failures
    // (auth/permission errors, wrong path, etc.), so failures are collected and
    // only ignored if at least one network came back with real SSID data.
    failures.push(
      net.name +
        " (" +
        net.id +
        "): status " +
        status +
        " - " +
        (ssidResponse || "").substring(0, 200),
    );
    return;
  }
  var ssids = JSON.parse(ssidResponse);
  ssids.forEach(function (ssid) {
    if (!ssid.enabled) {
      return;
    }
    data.push({
      "{#NETWORK_ID}": net.id,
      "{#NETWORK_NAME}": net.name,
      "{#SSID_NUMBER}": ssid.number,
      "{#SSID_NAME}": ssid.name,
    });
  });
});

if (data.length === 0 && failures.length > 0) {
  throw "No SSIDs found; per-network failures: " + failures.join(" | ");
}

return JSON.stringify({ data: data });
