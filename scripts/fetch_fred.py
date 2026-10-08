"""FRED-sarjat M2SL ja DTWEXBGS.

Ensisijaisesti virallinen API (vaatii ympäristömuuttujan FRED_API_KEY), varalla avaimeton
CSV-vienti (fredgraph.csv), joka ei vastaa kaikilta pilvipalvelimilta. API-avain ei saa päätyä
virheilmoituksiin, koska ne tallennetaan julkiseen fetch_status.json-tiedostoon."""
import io
import os

import pandas as pd

from common import http_get, last_date, load_config, merge_and_save

API_URL = "https://api.stlouisfed.org/fred/series/observations"
CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _scrub(err, key):
    """Virheviesti ilman API-avainta."""
    msg = f"{type(err).__name__}: {err}"
    return msg.replace(key, "***") if key else msg


def fetch_api(series_id, start, key, cfg):
    params = {"series_id": series_id, "api_key": key, "file_type": "json"}
    if start:
        params["observation_start"] = start
    fc = cfg["data"]
    j = http_get(API_URL, params=params, timeout=fc["fred_timeout_s"], retries=fc["fred_retries"]).json()
    obs = j.get("observations") or []
    return pd.DataFrame({
        "date": pd.to_datetime([o["date"] for o in obs]),
        "value": pd.to_numeric([o["value"] for o in obs], errors="coerce"),  # '.' = puuttuva
    })


def fetch_csv(series_id, start, cfg):
    params = {"id": series_id}
    if start:
        params["cosd"] = start
    fc = cfg["data"]
    raw = pd.read_csv(io.StringIO(
        http_get(CSV_URL, params=params, timeout=fc["fred_timeout_s"], retries=fc["fred_retries"]).text))
    return pd.DataFrame({
        "date": pd.to_datetime(raw[raw.columns[0]]),
        "value": pd.to_numeric(raw[series_id], errors="coerce"),
    })


def update_series(series_id, name, cfg):
    prev = last_date(name)
    # FRED revisioi tuoreita arvoja, joten haetaan päällekkäinen jakso uudelleen
    start = None if prev is None else \
        (prev - pd.Timedelta(days=cfg["data"]["fred_overlap_days"])).strftime("%Y-%m-%d")
    key = os.environ.get("FRED_API_KEY", "").strip()
    errors, via = [], None
    raw = None
    if key:
        try:
            raw, via = fetch_api(series_id, start, key, cfg), "api"
        except Exception as e:  # noqa: BLE001
            errors.append("API: " + _scrub(e, key))
    if raw is None:
        try:
            raw, via = fetch_csv(series_id, start, cfg), "csv"
        except Exception as e:  # noqa: BLE001
            errors.append("CSV: " + _scrub(e, key))
            raise RuntimeError(f"FRED {series_id}: " + " | ".join(errors)) from None
    new = raw.dropna().rename(columns={"value": name})
    if new.empty:
        raise RuntimeError(f"FRED {series_id}: ei rivejä")
    df, added = merge_and_save(name, new)
    return {"rows": len(df), "added": added, "last_date": df["date"].max().strftime("%Y-%m-%d"), "via": via}


def update_m2(cfg=None):
    return update_series("M2SL", "m2", cfg or load_config())


def update_dollar(cfg=None):
    return update_series("DTWEXBGS", "dollar", cfg or load_config())


if __name__ == "__main__":
    print(update_m2(), update_dollar())
