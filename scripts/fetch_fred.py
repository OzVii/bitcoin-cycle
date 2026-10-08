"""FRED-sarjat avaimettomana CSV-vientinä (fredgraph.csv): M2SL ja DTWEXBGS."""
import io

import pandas as pd

from common import http_get, last_date, load_config, merge_and_save

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def update_series(series_id, name, cfg):
    prev = last_date(name)
    params = {"id": series_id}
    if prev is not None:
        # FRED revisioi tuoreita arvoja, joten haetaan päällekkäinen jakso uudelleen
        params["cosd"] = (prev - pd.Timedelta(days=cfg["data"]["fred_overlap_days"])).strftime("%Y-%m-%d")
    text = http_get(URL, params=params).text
    raw = pd.read_csv(io.StringIO(text))
    date_col = raw.columns[0]
    new = pd.DataFrame({
        "date": pd.to_datetime(raw[date_col]),
        name: pd.to_numeric(raw[series_id], errors="coerce"),  # '.' = puuttuva
    }).dropna()
    if new.empty:
        raise RuntimeError(f"FRED {series_id}: ei rivejä")
    df, added = merge_and_save(name, new)
    return {"rows": len(df), "added": added, "last_date": df["date"].max().strftime("%Y-%m-%d")}


def update_m2(cfg=None):
    return update_series("M2SL", "m2", cfg or load_config())


def update_dollar(cfg=None):
    return update_series("DTWEXBGS", "dollar", cfg or load_config())


if __name__ == "__main__":
    print(update_m2(), update_dollar())
