import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_config(new_config: dict):
    config = load_config()
    config.update(new_config)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def write_config(config: dict):
    """Persist exactly provided config without merging with existing content."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def clear_credentials():
    config = load_config()
    config.pop("apiKey", None)
    config.pop("apiSecret", None)
    config.pop("user", None)
    config.pop("password", None)
    config.pop("site", None)
    write_config(config)


def persist_login_config(url: str, site: str, user: str, save_password: bool = False, password: str = ""):
    """Store auth settings while avoiding plaintext password persistence by default."""
    payload = {
        "serverUrl": url,
        "site": site,
        "user": user,
        "password": password if save_password else "",
        "apiKey": "",
        "apiSecret": "",
    }
    save_config(payload)
