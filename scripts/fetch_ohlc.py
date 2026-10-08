"""Päivä-OHLC kaaviota varten: Bitstamp ensisijainen, Kraken varalla (vain viim. 720 pv)."""
import time

import pandas as pd

from common import http_get, last_date, load_config, merge_and_save

NAME = "ohlc_daily"
COLS = ["date", "open", "high", "low", "close", "volume"]


def fetch_bitstamp(start_ts):
    rows = []
    now = int(time.time())
    ts = start_ts
    while ts < now:
        j = http_get("https://www.bitstamp.net/api/v2/ohlc/btcusd/",
                     params={"step": 86400, "limit": 1000, "start": ts}).json()
        batch = j.get("data", {}).get("ohlc", [])
        if not batch:
            break
        rows += batch
        last_ts = int(batch[-1]["timestamp"])
        if last_ts <= ts:
            break
        ts = last_ts + 86400
        time.sleep(0.5)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=COLS)
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.normalize()
    for c in COLS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[COLS]


def fetch_kraken(start_ts):
    j = http_get("https://api.kraken.com/0/public/OHLC",
                 params={"pair": "XBTUSD", "interval": 1440, "since": start_ts}).json()
    if j.get("error"):
        raise RuntimeError(f"Kraken: {j['error']}")
    key = [k for k in j["result"] if k != "last"][0]
    df = pd.DataFrame(j["result"][key], columns=["ts", "open", "high", "low", "close", "vwap", "volume", "count"])
    df["date"] = pd.to_datetime(df["ts"].astype(int), unit="s").dt.normalize()
    for c in COLS[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[COLS]


def update(cfg=None):
    cfg = cfg or load_config()
    src = cfg["data"]
    prev = last_date(NAME)
    start = pd.Timestamp(src["bitstamp_start"]) if prev is None else prev - pd.Timedelta(days=src["overlap_days"])
    start_ts = int(start.timestamp())
    source = "bitstamp"
    try:
        new = fetch_bitstamp(start_ts)
        if new.empty:
            raise RuntimeError("Bitstamp palautti tyhjän vastauksen")
    except Exception as e:  # noqa: BLE001
        if prev is None:
            raise  # Krakenilla ei saa koko historiaa
        print(f"  Bitstamp epäonnistui ({e}), käytetään Krakenia")
        new = fetch_kraken(start_ts)
        source = "kraken"
    df, added = merge_and_save(NAME, new)
    return {"rows": len(df), "added": added, "last_date": df["date"].max().strftime("%Y-%m-%d"), "via": source}


if __name__ == "__main__":
    print(update())
