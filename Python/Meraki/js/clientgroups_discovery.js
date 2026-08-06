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
networks.forEach(function (net) {
  var gpResponse = request.get(
    url + "networks/" + encodeURIComponent(net.id) + "/groupPolicies",
  );
  if (request.getStatus() !== 200) {
    return; // network doesn't support group policies (e.g. no eligible product) — skip it
  }
  var policies = JSON.parse(gpResponse);
  policies.forEach(function (gp) {
    data.push({
      "{#NETWORK_ID}": net.id,
      "{#NETWORK_NAME}": net.name,
      "{#GROUP_POLICY_ID}": gp.groupPolicyId,
      "{#GROUP_POLICY_NAME}": gp.name,
    });
  });
});

return JSON.stringify({ data: data });
