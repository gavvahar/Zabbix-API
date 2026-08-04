# Zabbix API

Small collection of Python helpers for pulling data out of the [Zabbix API](https://www.zabbix.com/documentation/current/en/manual/api).

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your values:

   ```bash
   cp .env.example .env
   ```

   - `ZABBIX_URL` — the JSON-RPC endpoint of your Zabbix server, e.g. `https://zabbix.example.com/api_jsonrpc.php`.
   - `ZABBIX_API_TOKEN` — a Zabbix API token ([how to generate one](https://www.zabbix.com/documentation/current/en/manual/web_interface/frontend_sections/users/api_tokens)), sent as a `Bearer` token (Zabbix 6.4+).
   - `ZABBIX_ORG_HOST` / `ZABBIX_TEST_HOST` — optional, only needed by [`Python/Meraki/provision.py`](Python/Meraki/provision.py)'s `rollout`/`test` actions (see below).

## Usage

```python
import hostgroups, hosts

hostgroups.get_hostgroups()
hostgroups.hostgroup_id("Linux servers")

hosts.get_hosts()
hosts.get_hosts("Linux servers")
```

- `lib.py` — shared API helpers: base URL, token, and a `call` JSON-RPC request wrapper.
- `hostgroups.py` — list host groups and look up a host group id by name.
- `hosts.py` — list hosts, optionally filtered to a host group.

### Meraki wireless monitoring

[`Python/Meraki/provision.py`](Python/Meraki/provision.py) provisions Meraki wireless monitoring in Zabbix end to end — cloning templates, adding items/triggers, and wiring up discovery rules — driven entirely by the API rather than manual template edits. Run it from the `Python/Meraki` directory:

```bash
cd Python/Meraki
python provision.py all         # runs create, ap-health, and wireless in sequence
python provision.py create      # clone the device template, add the packet loss item + trigger
python provision.py ap-health   # extend the clone: device status, AP Down, Firmware Outdated, High Latency, API Failure
python provision.py wireless    # clone the dashboard template, add Network/SSID/Radio discovery + triggers
python provision.py test        # force-run the packet loss item on ZABBIX_TEST_HOST and print the raw result
python provision.py rollout     # repoint the device-discovery host prototype at the clone (fleet-wide)
python provision.py rollback    # undo rollout
```

`test`, `rollout`, and `rollback` touch a real host or the fleet-wide discovery rule, so they're deliberately left out of `all` — run those one at a time.

Requires Zabbix 6.4+ (Script item type, item-level timeout override, `task.create` check-now). The implementation is split across sibling modules in `Python/Meraki/`:

- `config.py` — env vars, template names, tuning macros.
- `scripts.py` — the Zabbix Script item JavaScript bodies.
- `api.py` — Zabbix JSON-RPC wrapper and shared lookup/template helpers.
- `create.py`, `aphealth.py`, `wireless.py`, `ops.py` — one module per CLI action.

## Development

This repo uses [tox](https://tox.wiki/) for linting and formatting. Some checks (Prettier, Taplo) run via `npx`, so Node.js/npm are required — install the Node dependencies once:

```bash
npm install
```

Then run the full suite, which formats and fixes everything in place:

```bash
tox -e all
```

CI runs the check-only chain on every push via GitHub Actions (`.github/workflows/tests.yml`), equivalent to:

```bash
tox -e github
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for code style and PR guidelines.
