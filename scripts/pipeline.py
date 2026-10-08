"""Kokoaa päivä- ja viikkoaikasarjat indikaattoreineen tallennetusta historiasta.

Viikkotaulukon viimeinen rivi voi olla keskeneräinen viikko (complete=False). Kaikki
indikaattorit ovat kausaalisia, joten keskeneräinen rivi ei muuta aiempien rivien arvoja."""
import pandas as pd

import indicators as ind
from common import read_history

CM_RENAME = {"PriceUSD": "price", "CapMVRVCur": "mvrv", "CapMrktCurUSD": "mcap",
             "IssTotUSD": "iss", "SplyCur": "supply"}


def load_data():
    return {name: read_history(name) for name in ("coinmetrics", "ohlc_daily", "fng", "m2", "dollar")}


def _asof(daily, other, col, lag_days):
    """Liittää sarjan päivätauluun julkaisuviiveen kanssa (arvo tiedossa vasta date + lag)."""
    if other is None or other.empty:
        daily[col] = float("nan")
        return daily
    o = other[["date", col]].dropna().copy()
    o["known"] = o["date"] + pd.Timedelta(days=lag_days)
    o = o.drop(columns="date").sort_values("known")
    out = pd.merge_asof(daily.sort_values("date"), o, left_on="date", right_on="known", direction="backward")
    return out.drop(columns="known")


def build_daily(data, cfg):
    ic, dc = cfg["indicators"], cfg["data"]
    d = data["coinmetrics"].rename(columns=CM_RENAME)
    d = d.dropna(subset=["price", "mvrv", "mcap"]).sort_values("date").reset_index(drop=True)

    z = ind.mvrv_z(d["mcap"], d["mvrv"], ic["mvrv_z_min_days"], ic.get("mvrv_z_std_window_days"))
    d["realized_cap"], d["sigma"], d["mvrv_z"] = z["realized_cap"], z["sigma"], z["z"]
    d["realized_price"] = ind.realized_price(d["price"], d["mvrv"])
    d["puell"] = ind.puell(d["iss"], ic["puell_window_days"])
    pi = ind.pi_cycle(d["price"], ic["pi_short_days"], ic["pi_long_days"], ic["pi_multiplier"])
    d = pd.concat([d, pi], axis=1)
    d["last_pi_cross"] = d["date"].where(d["pi_cross"]).ffill()
    d["days_since_halving"] = ind.days_since_halving(d["date"], cfg["halvings"])

    # Fear & Greed (julkaistaan samana päivänä)
    fng = data.get("fng")
    if fng is not None and not fng.empty:
        d = d.merge(fng[["date", "fng"]], on="date", how="left")
        d["fng_avg"] = d["fng"].rolling(ic["fng_avg_days"], min_periods=ic["fng_avg_days"] // 2).mean()
        d["fng"] = d["fng"].ffill(limit=3)
    else:
        d["fng"] = d["fng_avg"] = float("nan")

    # Dollari-indeksi julkaisuviiveellä, 13 viikon muutos
    d = _asof(d, data.get("dollar"), "dollar", dc["dollar_release_lag_days"])
    d["dollar_13w_pct"] = (d["dollar"] / d["dollar"].shift(ic["dollar_change_days"]) - 1) * 100

    # M2: vuosimuutos ja sen kiihtyvyys kuukausitasolla, julkaisuviiveellä
    m2 = data.get("m2")
    if m2 is not None and not m2.empty:
        m = m2.sort_values("date").copy()
        m["m2_yoy"] = m["m2"].pct_change(12, fill_method=None) * 100
        m["m2_accel"] = m["m2_yoy"] - m["m2_yoy"].shift(ic["m2_accel_months"])
        m["m2_month"] = m["date"]
        d = _asof(d, m[["date", "m2_yoy"]], "m2_yoy", dc["m2_release_lag_days"])
        d = _asof(d, m[["date", "m2_accel"]], "m2_accel", dc["m2_release_lag_days"])
        d = _asof(d, m[["date", "m2_month"]], "m2_month", dc["m2_release_lag_days"])
    else:
        d["m2_yoy"] = d["m2_accel"] = float("nan")
        d["m2_month"] = pd.NaT
    return d.reset_index(drop=True)


def build_monthly(daily, cfg):
    ic = cfg["indicators"]
    m = ind.to_monthly_last(daily[["date", "price"]])
    m = m[m["complete"]].reset_index(drop=True)  # vain suljetut kuukaudet
    m["rsi_m"] = ind.rsi(m["price"], ic["rsi_period"])
    f, s, g = ic["macd"]
    mc = ind.macd(m["price"], f, s, g)
    m["macd_m"], m["macd_signal_m"], m["macd_hist_m"] = mc["macd"], mc["signal"], mc["hist"]
    m["macd_hist_prev_m"] = m["macd_hist_m"].shift(1)
    return m


def build_weekly(daily, cfg):
    ic = cfg["indicators"]
    w = ind.to_weekly_last(daily)
    c = w["price"]
    w["sma200w"] = ind.sma(c, ic["sma200w_weeks"])
    w["wma200_mult"] = c / w["sma200w"]
    w["sma20w"] = ind.sma(c, ic["band_sma_weeks"])
    w["ema21w"] = ind.ema(c, ic["band_ema_weeks"])
    w["band_top"] = w[["sma20w", "ema21w"]].max(axis=1, skipna=False)
    w["band_bottom"] = w[["sma20w", "ema21w"]].min(axis=1, skipna=False)
    band = ind.support_band_state(c, w["band_top"], w["band_bottom"], ic["trend_confirm_weeks"])
    w = pd.concat([w, band], axis=1)
    w["sma50w"] = ind.sma(c, ic["sma50w_weeks"])
    w["sma50w_slope"] = ind.slope_pct(w["sma50w"], ic["sma50w_slope_weeks"])
    w["rsi_w"] = ind.rsi(c, ic["rsi_period"])
    dv = ic["divergence"]
    div, events = ind.find_divergences(c, w["rsi_w"], dv["left_bars"], dv["right_bars"], dv["min_gap_weeks"],
                                       dv["max_gap_weeks"], dv["active_weeks"], dv["bear_min_rsi"],
                                       dv["bull_max_rsi"])
    w = pd.concat([w, div], axis=1)
    w["pi_cross_weeks_ago"] = (w["date"] - w["last_pi_cross"]).dt.days / 7
    dc = cfg["scoring"]["valuation"].get("cycle_decay", {})
    for key, col in dc.get("metrics", {}).items():
        w[f"ref_{col}"] = ind.prev_cycle_peak(w["date"], w[col], cfg["halvings"], dc.get("min_valid_weeks", 52))

    monthly = build_monthly(daily, cfg)
    mcols = ["date", "rsi_m", "macd_m", "macd_signal_m", "macd_hist_m", "macd_hist_prev_m"]
    w = pd.merge_asof(w.sort_values("date"), monthly[mcols].rename(columns={"date": "month_date"}),
                      left_on="date", right_on="month_date", direction="backward")
    div_events = [{"type": e["type"],
                   "confirmed": w.loc[e["confirmed_idx"], "week_start"].strftime("%Y-%m-%d"),
                   "pivot": w.loc[e["pivot_idx"], "week_start"].strftime("%Y-%m-%d"),
                   "prev": w.loc[e["prev_idx"], "week_start"].strftime("%Y-%m-%d")} for e in events]
    return w, monthly, div_events


def compute(data, cfg, as_of=None):
    """Koko laskenta. as_of (Timestamp) rajaa datan annettuun päivään asti (testit, backtest)."""
    if as_of is not None:
        data = {k: (v[v["date"] <= as_of] if v is not None else None) for k, v in data.items()}
    daily = build_daily(data, cfg)
    weekly, monthly, div_events = build_weekly(daily, cfg)
    return daily, weekly, monthly, div_events
