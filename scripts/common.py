"""Yhteiset apufunktiot: polut, config, CSV-historia ja HTTP."""
import json
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SITE_DATA_DIR = ROOT / "site" / "data"
CONFIG_PATH = ROOT / "config.json"
STATUS_PATH = DATA_DIR / "fetch_status.json"

USER_AGENT = {"User-Agent": "btc-sykli/1.0 (personal analysis tool)"}


def load_config(path=CONFIG_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def http_get(url, params=None, timeout=60, retries=3, backoff=5):
    """GET uudelleenyrityksillä. Palauttaa Response-olion tai nostaa viimeisimmän virheen."""
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=USER_AGENT, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise last


def read_history(name):
    """Lukee data/<name>.csv. Palauttaa None, jos tiedostoa ei ole."""
    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def merge_and_save(name, new):
    """Yhdistää uudet rivit historiaan. Päällekkäisillä päivillä uusi arvo voittaa."""
    old = read_history(name)
    if old is not None and len(old):
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    added = len(df) - (0 if old is None else len(old))
    return df, added


def last_date(name):
    df = read_history(name)
    if df is None or df.empty:
        return None
    return df["date"].max()


def load_status():
    if STATUS_PATH.exists():
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_status(status):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2, ensure_ascii=False)
