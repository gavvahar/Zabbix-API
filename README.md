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
