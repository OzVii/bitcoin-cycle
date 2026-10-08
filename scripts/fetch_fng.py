"""alternative.me Fear & Greed -indeksi (historia helmikuusta 2018)."""
import pandas as pd

from common import http_get, last_date, load_config, merge_and_save

NAME = "fng"


def update(cfg=None):
    cfg = cfg or load_config()
    prev = last_date(NAME)
    if prev is None:
        limit = 0  # koko historia
    else:
        limit = (pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - prev).days + cfg["data"]["overlap_days"]
    j = http_get("https://api.alternative.me/fng/", params={"limit": limit, "format": "json"}).json()
    data = j.get("data") or []
    if not data:
        raise RuntimeError(f"Fear & Greed: tyhjä vastaus ({j.get('metadata')})")
    new = pd.DataFrame(data)
    new["date"] = pd.to_datetime(new["timestamp"].astype(int), unit="s").dt.normalize()
    new["fng"] = pd.to_numeric(new["value"], errors="coerce")
    df, added = merge_and_save(NAME, new[["date", "fng"]])
    return {"rows": len(df), "added": added, "last_date": df["date"].max().strftime("%Y-%m-%d")}


if __name__ == "__main__":
    print(update())
