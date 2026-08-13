# Meraki JS Item Scripts

Maps each JavaScript item-value preprocessing script in this folder to the Python module that owns the Zabbix item it feeds, and what the item reports.

| JS file                    | Item key                                                  | Python module | Purpose                                                                                                             |
| -------------------------- | --------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------- |
| packet_loss.js             | `meraki.get.packetloss`                                   | create.py     | Runs an on-demand ping test via Meraki's live-ping-tool API; feeds both the latency and packet-loss dependent items |
| device_info.js             | `meraki.get.deviceinfo`                                   | aphealth.py   | Device metadata/health info                                                                                         |
| device_status.js           | `meraki.get.devicestatus`                                 | aphealth.py   | Device status — fallback path, **not used in the final device template**                                            |
| network_discovery.js       | `meraki.lld.networks`                                     | wireless.py   | LLD rule: discovers networks                                                                                        |
| network_connectionstats.js | `meraki.network.connectionstats[NID]`                     | wireless.py   | Connection stats for a network                                                                                      |
| network_latencystats.js    | `meraki.network.latencystats[NID]`                        | wireless.py   | Latency stats for a network                                                                                         |
| network_clientusage.js     | `meraki.network.usage[NID]`                               | wireless.py   | Client usage stats for a network                                                                                    |
| network_clientcount.js     | `meraki.network.clientcount[NID]` (bare scalar)           | wireless.py   | Client count for a network                                                                                          |
| network_authfailures.js    | `meraki.network.authfailures[NID]` (bare scalar)          | wireless.py   | Auth failure count for a network                                                                                    |
| ssid_discovery.js          | `meraki.lld.ssids`                                        | wireless.py   | LLD rule: discovers SSIDs                                                                                           |
| ssid_connectionstats.js    | `meraki.ssid.connectionstats[NID,SNUM]`                   | wireless.py   | Connection stats for an SSID                                                                                        |
| ssid_clientcount.js        | `meraki.ssid.clientcount[NID,SNUM]` (bare scalar)         | wireless.py   | Client count for an SSID                                                                                            |
| ssid_authfailures.js       | `meraki.ssid.authfailures[NID,SNUM]` (bare scalar)        | wireless.py   | Auth failure count for an SSID                                                                                      |
| radio_discovery.js         | `meraki.lld.radios`                                       | wireless.py   | LLD rule: discovers radios                                                                                          |
| radio_status.js            | `meraki.radio.status[SERIAL,BAND,IDX]`                    | wireless.py   | Status for a specific radio                                                                                         |
| radio_utilization.js       | `meraki.radio.utilization[SERIAL,BAND,IDX]` (bare scalar) | wireless.py   | Utilization for a specific radio                                                                                    |
| clientgroups_discovery.js  | `meraki.lld.clientgroups`                                 | wireless.py   | LLD rule: discovers client groups                                                                                   |
| clientgroup_detail.js      | `meraki.clientgroup.detail[NID,GPID]`                     | wireless.py   | Bandwidth limit detail for a client group policy                                                                    |

`config.py`, `api.py`, `ops.py`, `provision.py`, and `scripts.py` aren't referenced by any script here — none of the 18 JS files map to them, so presumably they're backend/provisioning logic not surfaced through these item-value scripts.
