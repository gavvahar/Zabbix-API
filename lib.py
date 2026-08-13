import os, requests
from dotenv import load_dotenv

load_dotenv()


def base_url():
    """Return the Zabbix API JSON-RPC endpoint URL from the environment."""
    return os.getenv("ZABBIX_URL")


def token():
    """Return the Zabbix API bearer token from the environment."""
    return os.getenv("ZABBIX_API_TOKEN")


def call(method, params=None):
    """Call a Zabbix API method over JSON-RPC and return the result, or None on error."""
    headers = {
        "Content-Type": "application/json-rpc",
        "Authorization": f"Bearer {token()}",
    }
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": 1,
    }

    response = None
    try:
        response = requests.post(base_url(), headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if "error" in body:
            print(f"Zabbix API error {body['error']['code']}: {body['error']['data']}")
            return None
        return body.get("result")

    except requests.exceptions.HTTPError:
        if response is not None:
            print(f"HTTP {response.status_code}")
            print(response.text)
    except Exception as e:
        print(e)

    return None
