"""`wireless` action — clones the dashboard template and adds Network/SSID/
Radio Discovery plus their trigger prototypes (High Client Count,
Authentication Failure Rate, Wireless Health Degraded).

Each discovery rule is a self-contained script covering its own API calls,
following the same flat-LLD pattern as the official "Devices discovery"
rule — Zabbix doesn't nest discovery rules, so SSID Discovery loops
networks internally rather than depending on Network Discovery's output.
"""

from api import api_call, clone_template, add_macros
from config import DASHBOARD_TEMPLATE, DASHBOARD_CLONE_TEMPLATE, DASHBOARD_MACROS
from scripts import (
    NETWORK_DISCOVERY_SCRIPT_BODY,
    SSID_DISCOVERY_SCRIPT_BODY,
    RADIO_DISCOVERY_SCRIPT_BODY,
    NETWORK_CLIENTCOUNT_SCRIPT_BODY,
    NETWORK_AUTHFAILURES_SCRIPT_BODY,
    SSID_AUTHFAILURES_SCRIPT_BODY,
    SSID_CLIENTCOUNT_SCRIPT_BODY,
    NETWORK_CONNECTIONSTATS_SCRIPT_BODY,
    SSID_CONNECTIONSTATS_SCRIPT_BODY,
    RADIO_UTILIZATION_SCRIPT_BODY,
    RADIO_STATUS_SCRIPT_BODY,
)


def create_discovery_rule(templateid, name, key, script_body, parameters, lifetime="7d"):
    """Create a Script discovery rule on the template, or return its existing id."""
    found = api_call("discoveryrule.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating discovery rule '{name}'")
    result = api_call(
        "discoveryrule.create",
        {
            "hostid": templateid,
            "name": name,
            "key_": key,
            "type": 21,  # Script
            "delay": "{$MERAKI.LLD.INTERVAL}",
            "timeout": "{$MERAKI.DATA.TIMEOUT}",
            "lifetime": lifetime,
            "params": script_body,
            "parameters": parameters,
        },
    )
    return result["itemids"][0]


def create_itemprototype(templateid, ruleid, name, key, script_body, parameters, value_type=3, units=None, history="31d", tags=None):
    """Create an item prototype under the discovery rule, or return its existing id."""
    found = api_call("itemprototype.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating item prototype '{name}'")
    payload = {
        "hostid": templateid,
        "ruleid": ruleid,
        "name": name,
        "key_": key,
        "type": 21,  # Script
        "value_type": value_type,  # 3 = Numeric unsigned
        "delay": "{$MERAKI.LLD.INTERVAL}",
        "timeout": "{$MERAKI.DATA.TIMEOUT}",
        "history": history,
        "params": script_body,
        "parameters": parameters,
    }
    if units:
        payload["units"] = units
    if tags:
        payload["tags"] = tags
    result = api_call("itemprototype.create", payload)
    return result["itemids"][0]


def create_dependent_itemprototype(templateid, ruleid, master_itemid, name, key, jsonpath, value_type=3, units=None, tags=None, bool_to_decimal=False):
    """Create a dependent item prototype that extracts jsonpath from the master item prototype's JSON, or return its existing id."""
    found = api_call("itemprototype.get", {"hostids": [templateid], "filter": {"key_": key}})
    if found:
        return found[0]["itemid"]

    print(f"Creating dependent item prototype '{name}'")
    preprocessing = [
        {
            "type": 12,  # JSONPath
            "params": jsonpath,
            "error_handler": 1,  # Discard value
            "error_handler_params": "",
        }
    ]
    if bool_to_decimal:
        # JSONPath alone hands Zabbix a literal true/false, which a numeric-typed
        # item rejects — this second step converts it to 1/0.
        preprocessing.append({"type": 6, "params": "", "error_handler": 0, "error_handler_params": ""})
    payload = {
        "hostid": templateid,
        "ruleid": ruleid,
        "name": name,
        "key_": key,
        "type": 18,  # Dependent item
        "master_itemid": master_itemid,
        "value_type": value_type,
        "history": "31d",
        "preprocessing": preprocessing,
    }
    if units:
        payload["units"] = units
    if tags:
        payload["tags"] = tags
    result = api_call("itemprototype.create", payload)
    return result["itemids"][0]


def create_trigger_prototype(templateid, description, expression, priority, tag_value="performance"):
    """Create a trigger prototype, or return its existing id."""
    found = api_call("triggerprototype.get", {"hostids": [templateid], "filter": {"description": description}})
    if found:
        return found[0]["triggerid"]

    print(f"Creating trigger prototype '{description}'")
    result = api_call(
        "triggerprototype.create",
        {
            "description": description,
            "expression": expression,
            "priority": priority,
            "tags": [{"tag": "scope", "value": tag_value}],
        },
    )
    return result["triggerids"][0]


def create_wireless_health(recreate=False):
    """Run the `wireless` action: clone the dashboard template and add Network/SSID/Radio discovery with their item and trigger prototypes."""
    templateid = clone_template(DASHBOARD_TEMPLATE, DASHBOARD_CLONE_TEMPLATE, recreate=recreate)
    add_macros(templateid, DASHBOARD_MACROS)

    api_params = [
        {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
        {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
        {"name": "token", "value": "{$MERAKI.TOKEN}"},
        {"name": "url", "value": "{$MERAKI.API.URL}"},
    ]
    network_tags = [{"tag": "component", "value": "network"}]
    ssid_tags = [{"tag": "component", "value": "ssid"}]
    radio_tags = [{"tag": "component", "value": "radio"}]

    # --- Network Discovery: client count + auth failures per network ---
    network_ruleid = create_discovery_rule(
        templateid,
        "Network Discovery",
        "meraki.lld.networks",
        NETWORK_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    clientcount_key = "meraki.network.clientcount[{#NETWORK_ID}]"
    create_itemprototype(
        templateid,
        network_ruleid,
        "Client count: {#NETWORK_NAME}",
        clientcount_key,
        NETWORK_CLIENTCOUNT_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        tags=network_tags,
    )
    net_authfail_key = "meraki.network.authfailures[{#NETWORK_ID}]"
    create_itemprototype(
        templateid,
        network_ruleid,
        "Auth failures (1h): {#NETWORK_NAME}",
        net_authfail_key,
        NETWORK_AUTHFAILURES_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        tags=network_tags,
    )
    net_connstats_itemid = create_itemprototype(
        templateid,
        network_ruleid,
        "Connection stats: {#NETWORK_NAME}",
        "meraki.network.connectionstats[{#NETWORK_ID}]",
        NETWORK_CONNECTIONSTATS_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        value_type=4,  # Text (raw JSON, mirrored by dependent items below)
        history="0",  # Do not store
        tags=network_tags,
    )
    create_dependent_itemprototype(
        templateid,
        network_ruleid,
        net_connstats_itemid,
        "DHCP failures (1h): {#NETWORK_NAME}",
        "meraki.network.dhcpfailures[{#NETWORK_ID}]",
        "$.result.dhcp",
        tags=network_tags,
    )
    create_dependent_itemprototype(
        templateid,
        network_ruleid,
        net_connstats_itemid,
        "DNS failures (1h): {#NETWORK_NAME}",
        "meraki.network.dnsfailures[{#NETWORK_ID}]",
        "$.result.dns",
        tags=network_tags,
    )
    create_dependent_itemprototype(
        templateid,
        network_ruleid,
        net_connstats_itemid,
        "Connection success rate (1h): {#NETWORK_NAME}",
        "meraki.network.connections.successrate[{#NETWORK_ID}]",
        "$.result.successRatePct",
        value_type=0,  # Numeric float
        units="%",
        tags=network_tags,
    )
    create_trigger_prototype(
        templateid,
        "Meraki: High client count on {#NETWORK_NAME}",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{clientcount_key})>{{$MERAKI.CLIENTCOUNT.HIGH}}",
        2,  # Warning
    )
    # Degraded = elevated network-wide auth failures, or client count well past the "high" watermark.
    # Deliberately doesn't fold in latency/packet loss — those live on the per-device template, a
    # different discovery rule's scope, and Zabbix trigger prototypes can't mix LLD contexts.
    create_trigger_prototype(
        templateid,
        "Meraki: Wireless health degraded on {#NETWORK_NAME}",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{net_authfail_key})>{{$MERAKI.AUTHFAIL.HIGH}} or last(/{DASHBOARD_CLONE_TEMPLATE}/{clientcount_key})>({{$MERAKI.CLIENTCOUNT.HIGH}}*2)",
        3,  # Average
    )

    # --- SSID Discovery: per-SSID auth failures ---
    ssid_ruleid = create_discovery_rule(
        templateid,
        "SSID Discovery",
        "meraki.lld.ssids",
        SSID_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    ssid_authfail_key = "meraki.ssid.authfailures[{#NETWORK_ID},{#SSID_NUMBER}]"
    create_itemprototype(
        templateid,
        ssid_ruleid,
        "Auth failures (1h): {#SSID_NAME} on {#NETWORK_NAME}",
        ssid_authfail_key,
        SSID_AUTHFAILURES_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "ssidnumber", "value": "{#SSID_NUMBER}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        tags=ssid_tags,
    )
    create_trigger_prototype(
        templateid,
        "Meraki: Authentication failure rate high on {#SSID_NAME} ({#NETWORK_NAME})",
        f"last(/{DASHBOARD_CLONE_TEMPLATE}/{ssid_authfail_key})>{{$MERAKI.AUTHFAIL.SSID.HIGH}}",
        2,  # Warning
    )
    create_itemprototype(
        templateid,
        ssid_ruleid,
        "Connected clients: {#SSID_NAME} on {#NETWORK_NAME}",
        "meraki.ssid.clientcount[{#NETWORK_ID},{#SSID_NUMBER}]",
        SSID_CLIENTCOUNT_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "ssidname", "value": "{#SSID_NAME}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        tags=ssid_tags,
    )
    ssid_connstats_itemid = create_itemprototype(
        templateid,
        ssid_ruleid,
        "Connection stats: {#SSID_NAME} on {#NETWORK_NAME}",
        "meraki.ssid.connectionstats[{#NETWORK_ID},{#SSID_NUMBER}]",
        SSID_CONNECTIONSTATS_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "networkid", "value": "{#NETWORK_ID}"},
            {"name": "ssidnumber", "value": "{#SSID_NUMBER}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        value_type=4,  # Text (raw JSON, mirrored by dependent items below)
        history="0",  # Do not store
        tags=ssid_tags,
    )
    create_dependent_itemprototype(
        templateid,
        ssid_ruleid,
        ssid_connstats_itemid,
        "DHCP failures (1h): {#SSID_NAME} on {#NETWORK_NAME}",
        "meraki.ssid.dhcpfailures[{#NETWORK_ID},{#SSID_NUMBER}]",
        "$.result.dhcp",
        tags=ssid_tags,
    )
    create_dependent_itemprototype(
        templateid,
        ssid_ruleid,
        ssid_connstats_itemid,
        "DNS failures (1h): {#SSID_NAME} on {#NETWORK_NAME}",
        "meraki.ssid.dnsfailures[{#NETWORK_ID},{#SSID_NUMBER}]",
        "$.result.dns",
        tags=ssid_tags,
    )
    create_dependent_itemprototype(
        templateid,
        ssid_ruleid,
        ssid_connstats_itemid,
        "Connection success rate (1h): {#SSID_NAME} on {#NETWORK_NAME}",
        "meraki.ssid.connections.successrate[{#NETWORK_ID},{#SSID_NUMBER}]",
        "$.result.successRatePct",
        value_type=0,  # Numeric float
        units="%",
        tags=ssid_tags,
    )

    # --- Radio Discovery: per-AP, per-band channel utilization (data only — not in the trigger list) ---
    radio_ruleid = create_discovery_rule(
        templateid,
        "Radio Discovery",
        "meraki.lld.radios",
        RADIO_DISCOVERY_SCRIPT_BODY,
        api_params,
    )
    create_itemprototype(
        templateid,
        radio_ruleid,
        # Meraki's utilization endpoint aggregates per band only, with no way to
        # distinguish APs that run two physical radios on the same band (5GHz is
        # common) — {#RADIO_INDEX} is only here to keep the item key unique per
        # discovered radio; both same-band radios legitimately report the same value.
        "Channel utilization: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        "meraki.radio.utilization[{#SERIAL},{#RADIO_BAND},{#RADIO_INDEX}]",
        RADIO_UTILIZATION_SCRIPT_BODY,
        [
            {"name": "band", "value": "{#RADIO_BAND}"},
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
            {"name": "serial", "value": "{#SERIAL}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        value_type=0,
        units="%",  # Numeric float
        tags=radio_tags,
    )
    radio_status_itemid = create_itemprototype(
        templateid,
        radio_ruleid,
        "Radio status: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        "meraki.radio.status[{#SERIAL},{#RADIO_BAND},{#RADIO_INDEX}]",
        RADIO_STATUS_SCRIPT_BODY,
        [
            {"name": "httpproxy", "value": "{$MERAKI.HTTP_PROXY}"},
            {"name": "orgid", "value": "{$MERAKI.ORG.ID}"},
            {"name": "serial", "value": "{#SERIAL}"},
            {"name": "token", "value": "{$MERAKI.TOKEN}"},
            {"name": "url", "value": "{$MERAKI.API.URL}"},
        ],
        value_type=4,  # Text (raw JSON, mirrored by dependent items below)
        history="0",  # Do not store
        tags=radio_tags,
    )
    radio_key = "{#SERIAL},{#RADIO_BAND},{#RADIO_INDEX}"
    radio_jsonkey = "{#RADIO_BAND}_{#RADIO_INDEX}"
    create_dependent_itemprototype(
        templateid,
        radio_ruleid,
        radio_status_itemid,
        "Channel: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        f"meraki.radio.channel[{radio_key}]",
        f"$.result.radios['{radio_jsonkey}'].channel",
        tags=radio_tags,
    )
    create_dependent_itemprototype(
        templateid,
        radio_ruleid,
        radio_status_itemid,
        "Channel width: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        f"meraki.radio.channelwidth[{radio_key}]",
        f"$.result.radios['{radio_jsonkey}'].channelWidth",
        units="MHz",
        tags=radio_tags,
    )
    create_dependent_itemprototype(
        templateid,
        radio_ruleid,
        radio_status_itemid,
        "TX power: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        f"meraki.radio.power[{radio_key}]",
        f"$.result.radios['{radio_jsonkey}'].power",
        units="dBm",
        tags=radio_tags,
    )
    # Serves both "Radio Enabled" and "SSID Broadcast Status" — Meraki's API only
    # exposes one signal here (per-SSID isBroadcasting, OR-reduced per radio in
    # RADIO_STATUS_SCRIPT_BODY), not two independently meaningful ones.
    create_dependent_itemprototype(
        templateid,
        radio_ruleid,
        radio_status_itemid,
        "Broadcasting: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        f"meraki.radio.broadcasting[{radio_key}]",
        f"$.result.radios['{radio_jsonkey}'].broadcasting",
        tags=radio_tags,
        bool_to_decimal=True,
    )
    create_dependent_itemprototype(
        templateid,
        radio_ruleid,
        radio_status_itemid,
        "SSIDs broadcasting: {#AP_NAME} ({#RADIO_BAND}GHz, radio {#RADIO_INDEX})",
        f"meraki.radio.ssids[{radio_key}]",
        f"$.result.radios['{radio_jsonkey}'].ssids",
        value_type=4,  # Text — a radio can broadcast multiple SSIDs at once
        tags=radio_tags,
    )

    print(f"Done. '{DASHBOARD_CLONE_TEMPLATE}' is ready (templateid {templateid}).")
    print("This only builds the template — it does not touch any live host.")
    print(f"Attach it to your org host yourself (replacing '{DASHBOARD_TEMPLATE}') to activate the LLD rules.")
