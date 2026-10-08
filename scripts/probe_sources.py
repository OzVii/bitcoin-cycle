"""Testaa datalähteet: saatavuus, historian pituus ja kentät.

Ajo: python scripts/probe_sources.py
FRED-API:n testaamiseen tarvitaan ympäristömuuttuja FRED_API_KEY (valinnainen).
"""
import json
import os
import sys
import time

import requests

UA = {"User-Agent": "btc-sykli-probe/0.1"}
TIMEOUT = 60
results = {}


def report(name, ok, **info):
    results[name] = {"ok": ok, **info}
    status = "OK " if ok else "FAIL"
    print(f"[{status}] {name}: {json.dumps(info, ensure_ascii=False, default=str)}")


def coinmetrics():
    base = "https://community-api.coinmetrics.io/v4"
    # Mitkä metriikat ovat community-tasolla saatavilla BTC:lle
    try:
        r = requests.get(f"{base}/catalog-v2/asset-metrics", params={"assets": "btc"}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        metrics = r.json()["data"][0]["metrics"]
        wanted = ["PriceUSD", "CapMVRVCur", "CapMrktCurUSD", "IssTotUSD", "CapRealUSD", "SplyCur"]
        avail = {}
        for m in metrics:
            if m["metric"] in wanted:
                avail[m["metric"]] = [f["frequency"] for f in m.get("frequencies", [])]
        report("coinmetrics_catalog", True, available=avail, missing=[w for w in wanted if w not in avail])
    except Exception as e:
        report("coinmetrics_catalog", False, error=str(e))

    for metric in ["PriceUSD", "CapMVRVCur", "CapMrktCurUSD", "IssTotUSD", "CapRealUSD", "SplyCur"]:
        try:
            rows, token, pages = [], None, 0
            while True:
                params = {"assets": "btc", "metrics": metric, "frequency": "1d",
                          "page_size": 10000, "start_time": "2009-01-01"}
                if token:
                    params["next_page_token"] = token
                r = requests.get(f"{base}/timeseries/asset-metrics", params=params, headers=UA, timeout=TIMEOUT)
                r.raise_for_status()
                j = r.json()
                rows += j["data"]
                pages += 1
                token = j.get("next_page_token")
                if not token or pages > 10:
                    break
                time.sleep(0.3)
            vals = [x for x in rows if x.get(metric) not in (None, "")]
            report(f"coinmetrics_{metric}", bool(vals), rows=len(rows), first=vals[0]["time"][:10] if vals else None,
                   last=vals[-1]["time"][:10] if vals else None, last_value=vals[-1][metric] if vals else None)
        except Exception as e:
            report(f"coinmetrics_{metric}", False, error=str(e))
        time.sleep(0.5)


def kraken():
    try:
        r = requests.get("https://api.kraken.com/0/public/OHLC", params={"pair": "XBTUSD", "interval": 10080},
                         headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        j = r.json()
        if j.get("error"):
            raise RuntimeError(j["error"])
        key = [k for k in j["result"] if k != "last"][0]
        c = j["result"][key]
        fmt = lambda t: time.strftime("%Y-%m-%d %a", time.gmtime(t))
        report("kraken_weekly_ohlc", True, pair=key, candles=len(c), first=fmt(c[0][0]), last=fmt(c[-1][0]),
               fields="time,open,high,low,close,vwap,volume,count")
    except Exception as e:
        report("kraken_weekly_ohlc", False, error=str(e))


def coingecko():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                         params={"vs_currency": "usd", "days": "365"}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        p = r.json()["prices"]
        report("coingecko_market_chart_365d", True, points=len(p))
    except Exception as e:
        report("coingecko_market_chart_365d", False, error=str(e))
    try:
        r = requests.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                         params={"vs_currency": "usd", "days": "max"}, headers=UA, timeout=TIMEOUT)
        report("coingecko_market_chart_max", r.ok, status=r.status_code, body=r.text[:200] if not r.ok else "ok")
    except Exception as e:
        report("coingecko_market_chart_max", False, error=str(e))


def binance():
    try:
        r = requests.get("https://api.binance.com/api/v3/klines",
                         params={"symbol": "BTCUSDT", "interval": "1w", "limit": 1000}, headers=UA, timeout=TIMEOUT)
        report("binance_weekly", r.ok, status=r.status_code, candles=len(r.json()) if r.ok else None)
    except Exception as e:
        report("binance_weekly", False, error=str(e))


def fng():
    try:
        r = requests.get("https://api.alternative.me/fng/", params={"limit": 0, "format": "json"},
                         headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        d = r.json()["data"]
        ts = sorted(int(x["timestamp"]) for x in d)
        fmt = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))
        report("alternative_me_fng", True, rows=len(d), first=fmt(ts[0]), last=fmt(ts[-1]),
               fields=list(d[0].keys()), latest=d[0]["value"])
    except Exception as e:
        report("alternative_me_fng", False, error=str(e))


def fred():
    for sid in ["M2SL", "DTWEXBGS"]:
        # Avaimeton CSV-vienti (fredgraph)
        try:
            r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid},
                             headers=UA, timeout=TIMEOUT)
            r.raise_for_status()
            lines = [l for l in r.text.strip().splitlines() if l]
            report(f"fred_csv_{sid}", True, rows=len(lines) - 1, header=lines[0], first=lines[1], last=lines[-1])
        except Exception as e:
            report(f"fred_csv_{sid}", False, error=str(e))
        key = os.environ.get("FRED_API_KEY")
        if key:
            try:
                r = requests.get("https://api.stlouisfed.org/fred/series/observations",
                                 params={"series_id": sid, "api_key": key, "file_type": "json"}, timeout=TIMEOUT)
                r.raise_for_status()
                o = r.json()["observations"]
                report(f"fred_api_{sid}", True, rows=len(o), first=o[0]["date"], last=o[-1]["date"])
            except Exception as e:
                report(f"fred_api_{sid}", False, error=str(e).replace(key, "***"))
        else:
            report(f"fred_api_{sid}", False, error="FRED_API_KEY puuttuu, ohitettu")


if __name__ == "__main__":
    for fn in (coinmetrics, kraken, coingecko, binance, fng, fred):
        fn()
    out = sys.argv[1] if len(sys.argv) > 1 else None
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
