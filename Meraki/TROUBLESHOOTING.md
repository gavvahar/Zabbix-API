# Troubleshooting: Wireless Health dashboard showing no data

Log of the bugs found (in order) while getting `dashboard_wireless_health.yaml` and
`device_packet_loss.yaml` working end to end on a live Zabbix 7.4 instance, and how each
was diagnosed. Kept for the next time discovery rules go "Not supported" or a dashboard
widget comes up blank.

## 1. Import rejected: `unexpected tag "triggers"`

**Symptom:** Zabbix rejected the import outright with
`Invalid tag "/zabbix_export/templates/template(1)": unexpected tag "triggers"`.

**Cause:** `triggers:` and `graphs:` are not valid children of a `template:` object in the
Zabbix 7.4 export schema.

- A trigger that references exactly one local item must be nested inside that item's own
  `triggers:` list.
- A trigger that references two or more items must live in a **top-level**
  `zabbix_export.triggers:` list (a sibling of `templates:`, not inside any template).
- `graphs:` is always a top-level `zabbix_export` key too, never nested in a template
  (this mirrors how `graph_prototypes` nests inside a `discovery_rule`, but plain
  `graphs` doesn't nest inside a `template` at all).

**How it was found:** pulled Zabbix's own server-side import validator source
(`C74ImportValidator.php`) and export builder (`CConfigurationExportBuilder.php`) from
`github.com/zabbix/zabbix` and read the schema/order directly, instead of guessing from
prior examples.

## 2. Import rejected: `unexpected constant "INFORMATION"`

**Cause:** the trigger priority enum value is `INFO`, not `INFORMATION`. Confirmed against
`ui/include/classes/xml/CXmlConstantName.php` in the same repo.

**Also found while there:** the classic (non-LLD) dashboard graph widget type is
`graphclassic`, not `graph` (`graphprototype` was already correct for the LLD version).
This one hadn't errored yet, just caught it via the same sweep.

## 3. Discovery rules stuck on "Not supported": Duktape syntax error

**Symptom:** all 4 LLD rules (Networks/SSIDs/Radios/Client Groups) showed
`Status: Not supported`, info icon: `Cannot compile script: SyntaxError: empty expression
not allowed (line 22)`.

**Cause:** Zabbix Script items run on Duktape (ES5.1), which rejects a trailing comma in a
multi-line function call's argument list — valid in modern JS (ES2017+), not in ES5.1.
The repo had no `.prettierrc`, so Prettier's default `trailingComma: "all"` was silently
inserting these into 17 of 18 files under `Meraki/js/` every time `tox -e format` ran.

**Fix:** added `.prettierrc.json` with `"trailingComma": "es5"` (valid in arrays/objects,
never in call arguments), reformatted, and re-synced the corrected scripts into the
templates' embedded `params:` blocks.

## 4. Discovery runs but 404s: unset org ID macro

**Symptom:** after fix #3, discovery rules compiled and ran, but errored with
`Cannot execute script: Failed to list networks: status 404`.

**Cause:** `{$MERAKI.ORG.ID}` on the host was still the literal placeholder string
`"CHANGE_IF_NEEDED"` from the template default — never overridden after import. This is
expected, not a bug: templates are declarative, linking one doesn't execute any code or
call the Meraki API, so there's no way for Zabbix to auto-populate an org ID from an API
key. (Contrast with `{$ORGANIZATION_ID}` on the *device* template, which the base
template's own "Devices discovery" LLD rule *does* auto-populate — but only for hosts
that LLD itself creates, which the dashboard host isn't.)

**Fix:** set `{$MERAKI.ORG.ID}` on the host to the real org ID (same value as
`MERAKI_ORG_ID` in `.env`, used by `provision.py`).

## 5. Discovery works, dashboard partially populates: wrong API endpoints in the JS

**Symptom:** after fix #4, most graphs populated, but SSID-page "Connection Success
Rate", "DHCP failures" and "DNS failures" stayed at `[no data]` even though sibling
items (client count, auth failures) on the same SSID worked fine.

**Cause:** `ssid_connectionstats.js` called
`/networks/{id}/wireless/ssids/{number}/connectionStats` — a URL that doesn't exist
anywhere in Meraki's API. The real endpoint is network-level, with the SSID selected via
a query parameter instead of a URL segment:
`/networks/{id}/wireless/connectionStats?timespan=3600&ssid={number}`.
(`network_connectionstats.js`, the network-level sibling script, already used the
correct form — only the per-SSID variant had the bug.)

**Also found in the same pass:** `radio_utilization.js` read `band.utilization`, which
isn't a field in the real API response — the actual field is `band.total.percentage`.
Not the cause of any "Not supported" state (radio items that failed were failing because
those specific device/band combos genuinely had no `byBand` entry in Meraki's response,
which looks like real no-data rather than a bug), but it was silently returning `0`
whenever data *did* exist.

**How it was found:** downloaded Meraki's official OpenAPI spec
(`github.com/meraki/openapi`, `openapi/spec3.json`) and grepped it for every path
containing `connectionStats` / `channelUtilization` to get the real, current endpoint
shapes instead of guessing.

**Fix:** rewrote the URL in `ssid_connectionstats.js` and the field access in
`radio_utilization.js`, re-synced both into `dashboard_wireless_health.yaml`.

## Useful diagnostic moves for next time

- **Discovery rule "Not supported"**: click the small `i` info icon in the Status column
  — it shows the exact compile/runtime error.
- **A specific item stuck with no data, but no error state either**: check its `History`
  setting first. Raw/master Script items in these templates intentionally use
  `History: Do not store` (they only exist to feed `DEPENDENT` items via preprocessing),
  so Latest Data will never show a "last value" for them even when they're working —
  that's expected, not a bug.
- **Getting the actual error/output of a Script item without waiting for its next
  poll interval**: open the item, click **Test** → **Get value and test**. Runs it
  immediately against the real host and shows the raw error or return value, independent
  of the item's `History` setting.
- **Forcing a discovery rule or item to run immediately** instead of waiting for its
  interval: select it in the list view and click **Execute now**. Note the displayed
  `Not supported` status/error is sticky — it only updates on the *next* execution, so
  after fixing something you need to Execute now (or wait out the interval) before the
  status will reflect the fix.
- **Verifying a fix actually landed on the live instance** vs. just in the repo: open the
  item/discovery rule's script editor in the Zabbix UI directly and read the live script
  body — don't trust that a re-import succeeded just because the import screen said so.
- **When in doubt about a Meraki API URL or response shape**, check the real spec
  (`github.com/meraki/openapi`) rather than trusting an old script or memory — two of the
  bugs above were exactly this kind of drift.
