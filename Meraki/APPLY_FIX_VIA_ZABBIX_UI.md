# Applying the connection-stats / radio-utilization fix from the Zabbix UI

This is the same fix as the `ssid_connectionstats.js` / `radio_utilization.js` changes in
the repo (see `TROUBLESHOOTING.md`, section 5), applied directly in the Zabbix web UI
instead of via git + re-import. Do this if you want the live instance fixed right now
without waiting on a PR merge and re-import.

Both scripts are edited on the **item prototype** (one place per discovery rule), not on
each of the individual discovered items — Zabbix propagates a prototype's script down to
every item it already created the next time that discovery rule runs.

## Fix 1: SSID connection stats

1. **Data collection → Hosts** → click **Meraki Prod**.
2. Click **Discovery** (top tab bar) → click **SSID Discovery**.
3. Click **Item prototypes** (top tab bar) → click **Connection stats: {#SSID_NAME} on
   {#NETWORK_NAME}**.
4. In the **Script** field, click the small expand icon to open the code editor.
5. Find this block (around line 24-30):

   ```js
   var response = request.get(
     url +
       "networks/" +
       encodeURIComponent(params.networkid) +
       "/wireless/ssids/" +
       encodeURIComponent(params.ssidnumber) +
       "/connectionStats?timespan=3600"
   );
   ```

   Replace it with:

   ```js
   var response = request.get(
     url +
       "networks/" +
       encodeURIComponent(params.networkid) +
       "/wireless/connectionStats?timespan=3600&ssid=" +
       encodeURIComponent(params.ssidnumber)
   );
   ```

6. Click **Apply** on the code editor, then **Update** on the item prototype form.

## Fix 2: Radio channel utilization

1. Same host → **Discovery** → click **Radio Discovery**.
2. **Item prototypes** → click **Channel utilization: {#AP_NAME} ({#RADIO_BAND}GHz, radio
   {#RADIO_INDEX})**.
3. Open the **Script** editor.
4. Find the last line:

   ```js
   return band.utilization != null ? band.utilization : 0;
   ```

   Replace it with:

   ```js
   return band.total && band.total.percentage != null ? band.total.percentage : 0;
   ```

5. **Apply**, then **Update**.

## Propagate to already-discovered items

Editing a prototype doesn't retroactively touch the items it already created until
discovery runs again:

1. **Data collection → Hosts → Meraki Prod → Discovery**.
2. Select the checkboxes for **SSID Discovery** and **Radio Discovery**.
3. Click **Execute now**.
4. Wait 10-15 seconds, then refresh.

## Verify

1. **Monitoring → Latest data**, filter to host **Meraki Prod**, search name
   `connection stats` or `channel utilization` — the master items should show a recent
   **Last check** timestamp.
2. Open the **Meraki: Wireless Health** dashboard on the host (Monitoring → Hosts →
   Meraki Prod → Dashboards) and check the **SSIDs** page: "Connection Success Rate" and
   the DHCP/DNS lines on "Failures" should now show real values instead of `[no data]`.

## Keeping the repo in sync

This UI edit only changes the live Zabbix config — it does **not** update the git repo.
If you apply the fix this way, the next time these templates get re-imported from the
repo (e.g. after some other unrelated change), the old buggy scripts will overwrite this
fix again, since the repo's `dashboard_wireless_health.yaml` still has the old versions
until PR `fix/ssid-connectionstats-and-radio-utilization` is merged. Either merge that PR
before the next re-import, or reapply this UI fix afterward.
