"""CoinMetrics Community API: päivähinta, MVRV, markkina-arvo, liikkeeseenlasku, tarjonta."""
import pandas as pd

from common import http_get, last_date, load_config, merge_and_save

NAME = "coinmetrics"
BASE = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"


def fetch(metrics, start):
    rows, token = [], None
    while True:
        params = {"assets": "btc", "metrics": ",".join(metrics), "frequency": "1d",
                  "page_size": 10000, "start_time": start}
        if token:
            params["next_page_token"] = token
        j = http_get(BASE, params=params).json()
        rows += j.get("data", [])
        token = j.get("next_page_token")
        if not token:
            break
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", *metrics])
    df["date"] = pd.to_datetime(df["time"].str[:10])
    for m in metrics:
        df[m] = pd.to_numeric(df.get(m), errors="coerce")
    return df[["date", *metrics]]


def update(cfg=None):
    cfg = cfg or load_config()
    src = cfg["data"]
    prev = last_date(NAME)
    if prev is None:
        start = src["coinmetrics_start"]
    else:
        start = (prev - pd.Timedelta(days=src["overlap_days"])).strftime("%Y-%m-%d")
    new = fetch(src["coinmetrics_metrics"], start)
    df, added = merge_and_save(NAME, new)
    return {"rows": len(df), "added": added, "last_date": df["date"].max().strftime("%Y-%m-%d")}


if __name__ == "__main__":
    print(update())
