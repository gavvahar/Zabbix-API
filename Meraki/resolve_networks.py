"""Resolve Meraki network ids from human-readable names and write them into
the {$MERAKI.NETWORK.ID.PLB}/{$MERAKI.NETWORK.ID.HYD} macros on
DASHBOARD_CLONE_TEMPLATE.

One-time (or on-demand) setup step -- NOT a recurring job. A network's
Meraki id never changes unless the network itself is deleted and recreated,
and the 8 PLB/HYD discovery rule variants were deliberately simplified in
6c2482a to cut Meraki API load; adding a per-poll or per-cache-expiry
lookup here would regress that fix for no benefit. Re-run this manually
only if a network is deleted and recreated under the same name.

Requires MERAKI_API_TOKEN and MERAKI_ORG_ID (see config.py / .env.example)
-- separate from Zabbix's own {$MERAKI.TOKEN} macro, since this talks to
the Meraki API directly, outside Zabbix, like the rest of Meraki/*.py.
"""

import requests

from api import get_template_id, set_macro_value
from config import MERAKI_API_TOKEN, MERAKI_ORG_ID, DASHBOARD_CLONE_TEMPLATE, NETWORK_NAME_MACROS

MERAKI_API_BASE = "https://api.meraki.com/api/v1"


def _fetch_networks():
    """Return every network in MERAKI_ORG_ID as the Meraki API's raw list of
    {"id": ..., "name": ..., ...} dicts.

    Meraki paginates this endpoint at a default of 1000/page -- perPage=100000
    (the documented max) is passed explicitly so an org with more networks
    than that default doesn't get silently truncated, which would otherwise
    show up as a false "network not found" for a real network that just
    happened to fall past the first page.
    """
    url = f"{MERAKI_API_BASE}/organizations/{MERAKI_ORG_ID}/networks"
    headers = {"X-Cisco-Meraki-API-Key": MERAKI_API_TOKEN}
    resp = requests.get(url, headers=headers, params={"perPage": 100000}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def resolve_networks():
    """Resolve each NETWORK_NAME_MACROS entry to a real Meraki network id via
    one GET to the org's networks list, then write each result into the
    matching macro on DASHBOARD_CLONE_TEMPLATE.
    """
    if not MERAKI_API_TOKEN:
        raise RuntimeError("MERAKI_API_TOKEN is not set (see .env.example) -- required for resolve-networks.")
    if not MERAKI_ORG_ID or MERAKI_ORG_ID == "CHANGE_IF_NEEDED":
        raise RuntimeError("MERAKI_ORG_ID is not set (see .env.example) -- required for resolve-networks.")

    networks = _fetch_networks()

    # name (lowercased/stripped) -> list of ids, so a duplicate name in the
    # org is caught and reported instead of silently resolved to whichever
    # one happened to come back first.
    by_name = {}
    for net in networks:
        by_name.setdefault(net["name"].strip().lower(), []).append(net["id"])

    templateid = get_template_id(DASHBOARD_CLONE_TEMPLATE)

    for macro, name in NETWORK_NAME_MACROS.items():
        matches = by_name.get(name.strip().lower(), [])
        if not matches:
            raise RuntimeError(
                f"No Meraki network named '{name}' found in org {MERAKI_ORG_ID} (needed for {macro}). "
                f"Check NETWORK_NAME_MACROS in config.py against the real network name in the Meraki dashboard."
            )
        if len(matches) > 1:
            raise RuntimeError(
                f"Found {len(matches)} Meraki networks named '{name}' in org {MERAKI_ORG_ID} (needed for {macro}) -- "
                f"Meraki allows duplicate network names, so this can't be resolved automatically. "
                f"Rename one of them in the Meraki dashboard, or set {macro} manually."
            )

        old_value, new_value = set_macro_value(templateid, macro, matches[0])
        if old_value is None:
            print(f"{macro}: (none) -> {new_value}")
        else:
            print(f"{macro}: {old_value} -> {new_value}")


if __name__ == "__main__":
    resolve_networks()
