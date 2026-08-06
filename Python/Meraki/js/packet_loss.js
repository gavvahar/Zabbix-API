var params = JSON.parse(value);

var request = new HttpRequest();
request.addHeader("X-Cisco-Meraki-API-Key:" + params.token);
request.addHeader("Content-Type: application/json");
request.addHeader("User-Agent: ZabbixServer/1.2 Zabbix");

if (typeof params.httpproxy !== "undefined" && params.httpproxy !== "") {
  request.setProxy(params.httpproxy);
}

if (params.token === "{" + "MERAKI.TOKEN}") {
  throw "Please change {MERAKI.TOKEN} macro to the proper value.";
}

if (
  params.url.indexOf("http://") === -1 &&
  params.url.indexOf("https://") === -1
) {
  params.url = "https://" + params.url;
}
if (params.url.slice(-1) !== "/") {
  params.url = params.url + "/";
}

var error_msg = "";
var result = {};

function getHttpData(method, url, body) {
  var response;
  if (method === "POST") {
    response = request.post(url, JSON.stringify(body));
  } else {
    response = request.get(url);
  }
  var status = request.getStatus();
  Zabbix.log(
    4,
    "[ Meraki API ] [ " +
      url +
      " ] Received response with status code " +
      status +
      ": " +
      response,
  );

  var parsed = null;
  if (response !== null && response !== "") {
    parsed = JSON.parse(response);
  }
  if (status !== 200 && status !== 201) {
    if (parsed !== null && parsed.errors) {
      throw parsed.errors.join(", ");
    }
    throw (
      "Failed to receive data: invalid response status code " + status + "."
    );
  }
  return parsed === null ? {} : parsed;
}

try {
  var createBody = {
    count: parseInt(params.count, 10) || 5,
    target: params.target,
  };

  var baseUrl =
    params.url +
    "devices/" +
    encodeURIComponent(params.serial) +
    "/liveTools/ping";
  var createResp = getHttpData("POST", baseUrl, createBody);

  if (!createResp.pingId) {
    throw "Failed to create ping job: no pingId returned.";
  }

  var pollUrl = baseUrl + "/" + createResp.pingId;
  var maxAttempts = 15;
  var attempt = 0;

  while (attempt < maxAttempts) {
    Zabbix.sleep(2000);
    result = getHttpData("GET", pollUrl, null);
    if (result.status === "complete" || result.status === "failed") {
      break;
    }
    attempt++;
  }

  if (result.status !== "complete") {
    throw "Ping test did not complete in time. Last status: " + result.status;
  }
} catch (error) {
  error_msg = error.toString();
}

return JSON.stringify({
  result: result,
  error: error_msg,
});
