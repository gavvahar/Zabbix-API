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
      "/wireless/latencyStats?timespan=3600",
  );
  if (request.getStatus() !== 200) {
    throw "Failed to get latency stats: status " + request.getStatus();
  }
  var stats = JSON.parse(response);
  result = {
    voice:
      stats.voiceTraffic && stats.voiceTraffic.avg != null
        ? stats.voiceTraffic.avg
        : 0,
    video:
      stats.videoTraffic && stats.videoTraffic.avg != null
        ? stats.videoTraffic.avg
        : 0,
    bestEffort:
      stats.bestEffortTraffic && stats.bestEffortTraffic.avg != null
        ? stats.bestEffortTraffic.avg
        : 0,
    background:
      stats.backgroundTraffic && stats.backgroundTraffic.avg != null
        ? stats.backgroundTraffic.avg
        : 0,
  };
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  result: result,
  error: error_msg,
});
