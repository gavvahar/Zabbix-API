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

// Uses the SSID-status-by-device endpoint (not channelUtilization/byDevice)
// specifically because it exposes each radio's index — some APs run two
// physical radios on the same band (e.g. dual 5GHz), which channel
// utilization alone can't distinguish. {#RADIO_INDEX} is what makes those
// radios discoverable as separate entities instead of colliding.
var response = request.get(
  url +
    "organizations/" +
    encodeURIComponent(params.orgid) +
    "/wireless/ssids/statuses/byDevice?perPage=500",
);
if (request.getStatus() !== 200) {
  throw "Failed to list radio statuses: status " + request.getStatus();
}

var result = JSON.parse(response);
var seen = {};
var data = [];
(result.items || []).forEach(function (device) {
  (device.basicServiceSets || []).forEach(function (bss) {
    if (!bss.radio) {
      return;
    }
    var key = device.serial + ":" + bss.radio.band + ":" + bss.radio.index;
    if (seen[key]) {
      return;
    }
    seen[key] = true;
    data.push({
      "{#SERIAL}": device.serial,
      "{#AP_NAME}": device.name || device.serial,
      "{#RADIO_BAND}": bss.radio.band,
      "{#RADIO_INDEX}": bss.radio.index,
    });
  });
});

return JSON.stringify({ data: data });
