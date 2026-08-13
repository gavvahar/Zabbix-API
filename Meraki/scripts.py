"""Loads the Zabbix Script item JavaScript bodies from the js/ directory.

Each file under js/ is the complete, standalone script text uploaded
verbatim into a Script item's "params" field — there's no module system on
the Zabbix side, so each one is self-contained rather than sharing includes.

Meraki endpoint/field names used across the scripts (devices/statuses,
wireless/ssids, wireless/failedConnections,
wireless/devices/channelUtilization/byDevice) are best-effort from the
public Dashboard API v1 and were NOT verified against a live org — check
field names/response shape against current Meraki docs before running
against production.
"""

import os

_JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js")


def _read_js(filename):
    """Read and strip a script body from the js/ directory."""
    with open(os.path.join(_JS_DIR, filename)) as f:
        return f.read().strip()


# Reconstructed clean from instructions.md (stray ``` markers in that doc's
# code block were formatting artifacts and would break the script as-is).
SCRIPT_BODY = _read_js("packet_loss.js")

DEVICE_STATUS_SCRIPT_BODY = _read_js("device_status.js")
DEVICE_INFO_SCRIPT_BODY = _read_js("device_info.js")

NETWORK_DISCOVERY_SCRIPT_BODY = _read_js("network_discovery.js")
SSID_DISCOVERY_SCRIPT_BODY = _read_js("ssid_discovery.js")
RADIO_DISCOVERY_SCRIPT_BODY = _read_js("radio_discovery.js")
CLIENTGROUPS_DISCOVERY_SCRIPT_BODY = _read_js("clientgroups_discovery.js")

# Field names (bandwidth.bandwidthLimits.limitUp/limitDown) are per Meraki's
# official docs — NOT verified against a live example, since no group policy
# currently exists in this org to test against. Adjust if these turn out to
# be nested differently once a real policy exists.
CLIENTGROUP_DETAIL_SCRIPT_BODY = _read_js("clientgroup_detail.js")

# Per-AP raw status pull, aggregated by (band, index) since multiple SSIDs
# share the same physical radio and report identical channel/width/power —
# only 'broadcasting' varies per SSID, so it's OR-reduced across SSIDs on
# that radio here rather than picking an arbitrary single SSID's value.
RADIO_STATUS_SCRIPT_BODY = _read_js("radio_status.js")

NETWORK_CLIENTCOUNT_SCRIPT_BODY = _read_js("network_clientcount.js")
SSID_CLIENTCOUNT_SCRIPT_BODY = _read_js("ssid_clientcount.js")
NETWORK_AUTHFAILURES_SCRIPT_BODY = _read_js("network_authfailures.js")
SSID_AUTHFAILURES_SCRIPT_BODY = _read_js("ssid_authfailures.js")

# connectionStats buckets (assoc/auth/dhcp/dns) are each a count of clients that
# FAILED at that funnel step; 'success' is clients that completed the whole
# funnel. successRatePct is computed here (rather than via item preprocessing)
# so only the already-used JSONPath preprocessing type is needed downstream.
NETWORK_CONNECTIONSTATS_SCRIPT_BODY = _read_js("network_connectionstats.js")
SSID_CONNECTIONSTATS_SCRIPT_BODY = _read_js("ssid_connectionstats.js")

NETWORK_LATENCYSTATS_SCRIPT_BODY = _read_js("network_latencystats.js")

# wireless/usageHistory rejects network-wide calls outright ("Must specify a
# device or network client", confirmed against the live API — its own docs
# are misleading here). Per-client usage from /clients (already used for
# client count) sums cleanly into network-wide throughput instead.
NETWORK_CLIENTUSAGE_SCRIPT_BODY = _read_js("network_clientusage.js")

RADIO_UTILIZATION_SCRIPT_BODY = _read_js("radio_utilization.js")
