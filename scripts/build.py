"""Laskee indikaattorit, pisteet, vaiheet, alueet ja selitykset ja kirjoittaa
site/data/latest.json ja site/data/history.json."""
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import explanations as ex
import indicators as ind
import pipeline
import scoring
from common import SITE_DATA_DIR, load_config, load_status


# ---------------------------------------------------------------- arviointi

def evaluate(cfg, data=None, as_of=None):
    """Laskee kaiken. Palauttaa dictin, jota build ja backtest_report käyttävät."""
    data = data if data is not None else pipeline.load_data()
    daily, weekly, monthly, div_events = pipeline.compute(data, cfg, as_of=as_of)
    tracker = scoring.PhaseTracker(cfg)
    official = []
    for _, row in weekly[weekly["complete"]].iterrows():
        r = row.to_dict()
        sc = scoring.score_row(r, cfg)
        phase, cand = tracker.step(sc["layers"]["valuation"]["score"], sc["total"], r.get("trend"),
                                   r.get("fng_avg"), bool(r.get("div_bear")))
        official.append({"row": r, "scored": sc, "phase": phase, "candidate": cand})
    preview = None
    last = weekly.iloc[-1]
    if not last["complete"]:
        r = last.to_dict()
        sc = scoring.score_row(r, cfg)
        phase, cand = tracker.copy().step(sc["layers"]["valuation"]["score"], sc["total"], r.get("trend"),
                                          r.get("fng_avg"), bool(r.get("div_bear")))
        preview = {"row": r, "scored": sc, "phase": phase, "candidate": cand}
    ic = cfg["indicators"]
    cycles = ind.find_cycles(daily, cfg["halvings"], ic["cycle_top_window_days"], ic["cycle_bottom_window_days"],
                             ic["cycle_top_confirm_drawdown"])
    return {"daily": daily, "weekly": weekly, "monthly": monthly, "div_events": div_events,
            "official": official, "preview": preview, "cycles": cycles}


def cycle_reference(ev):
    """Mittarien arvot aiempien vahvistettujen syklien huipuissa ja pohjissa (selityksiä varten)."""
    daily = ev["daily"].set_index("date")
    weekly = ev["weekly"]

    def snap(date, year):
        date = pd.Timestamp(date)
        d = daily.loc[date] if date in daily.index else None
        wk = weekly[(weekly["week_start"] <= date) & (weekly["week_end"] >= date)]
        w = wk.iloc[0] if len(wk) else None
        return {
            "year": year, "date": date.strftime("%Y-%m-%d"),
            "price": None if d is None else float(d["price"]),
            "mvrv_z": None if d is None else float(d["mvrv_z"]),
            "puell": None if d is None else float(d["puell"]),
            "fng_avg": None if d is None else float(d["fng_avg"]),
            "wma200_mult": None if w is None or pd.isna(w["sma200w"]) or d is None else float(d["price"] / w["sma200w"]),
            "rsi_w": None if w is None else float(w["rsi_w"]),
        }

    tops = [snap(c["top_date"], int(c["top_date"][:4])) for c in ev["cycles"] if c["top_confirmed"]]
    bottoms = [snap(c["bottom_date"], int(c["bottom_date"][:4])) for c in ev["cycles"]]
    clean = lambda L: [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in i.items()} for i in L]
    return {"tops": clean(tops), "bottoms": clean(bottoms)}


# ---------------------------------------------------------------- apurit

def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if (math.isnan(x) or math.isinf(x)) else float(x)
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.strftime("%Y-%m-%d")
    if x is pd.NaT:
        return None
    return x


def sig(x, n=6):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return float(f"{x:.{n}g}")


def ts(d):
    return int(pd.Timestamp(d).timestamp())


def metric(key, label, value, info=None):
    return {"key": key, "label": label, "value": value, "info": info or key}


def layer_metrics(r):
    trend_state = {"above": "above", "below": "below", "inside": "inside"}.get(r.get("band_state"), "–")
    div = "bearish" if r.get("div_bear") else "bullish" if r.get("div_bull") else "none active"
    return {
        "valuation": [
            metric("wma200", "Price / 200W SMA", ex.fnum(r.get("wma200_mult"), 2) + "×"),
            metric("mvrv_z", "MVRV Z-score", ex.fnum(r.get("mvrv_z"), 2)),
            metric("realized_price", "Realized price", ex.fusd(r.get("realized_price"))),
            metric("puell", "Puell Multiple", ex.fnum(r.get("puell"), 2)),
            metric("pi_cycle", "Pi Cycle distance", ex.fpct(r.get("pi_dist_pct"), 0, sign=False)),
            metric("halving", "Days since halving", f"{ex.fnum(r.get('days_since_halving'), 0)} days"),
        ],
        "trend": [
            metric("support_band", "Support band", f"{ex.fusd(r.get('band_bottom'))}–{ex.fusd(r.get('band_top'))}"),
            metric("support_band", "Weekly close vs band", f"{trend_state} ({r.get('band_streak')} wk)"),
            metric("sma50w", "50W SMA", ex.fusd(r.get("sma50w"))),
            metric("sma50w", "50W SMA slope (4 wk)", ex.fpct(r.get("sma50w_slope"))),
        ],
        "momentum": [
            metric("rsi", "Weekly RSI", ex.fnum(r.get("rsi_w"), 0)),
            metric("rsi", "Monthly RSI", ex.fnum(r.get("rsi_m"), 0)),
            metric("macd", "Monthly MACD histogram", ex.fnum(r.get("macd_hist_m"), 0)),
            metric("divergence", "RSI divergence", div),
        ],
        "sentiment": [
            metric("fng", "Fear & Greed", f"{ex.fnum(r.get('fng'), 0)} ({ex.fng_class(r.get('fng'))})"),
            metric("fng", "4-week average", ex.fnum(r.get("fng_avg"), 0)),
        ],
        "macro": [
            metric("m2", "M2 year on year", ex.fpct(r.get("m2_yoy"))),
            metric("m2", "M2 acceleration (3 mo)", f"{ex.fnum(r.get('m2_accel'), 1)} pp"),
            metric("dollar", "Dollar index (13 wk)", ex.fpct(r.get("dollar_13w_pct"))),
        ],
    }


def signal_block(item, cfg, hist, cycles, current_price):
    r, sc, phase = item["row"], item["scored"], item["phase"]
    zones = scoring.zones(r, cfg, current_price)
    texts = ex.layer_texts(r, sc, hist, cfg)
    texts["valuation"] += " " + ex.cycle_timing_text(r.get("days_since_halving"), cfg["halvings"][-1], cycles)
    metrics = layer_metrics(r)
    dz = sc["layers"]["valuation"].get("decay", {}).get("mvrv_z")
    if dz and not math.isnan(dz["anchor_x"]):
        metrics["valuation"].append(metric("cycle_decay", "MVRV Z sell threshold (−60 pts)",
                                           f"{ex.fnum(dz['anchor_x'], 2)} (×{ex.fnum(dz['scale'], 2)})"))
    layers = [{
        "key": k, "name": ex.LAYER_NAMES[k], "score": sc["layers"][k]["score"],
        "weight": sc["layers"][k]["weight"], "nominal_weight": cfg["scoring"]["layer_weights"][k],
        "components": sc["layers"][k]["components"], "text": texts[k].strip(), "metrics": metrics[k],
    } for k in scoring.LAYERS]
    return {
        "week_start": r["week_start"], "week_end": r["week_end"], "close_date": r["date"], "close": r["price"],
        "total": sc["total"], "phase": phase, "phase_name": cfg["phases"]["names"][str(phase)],
        "phase_candidate": item["candidate"], "layers": layers, "zones": zones,
    }


# ---------------------------------------------------------------- pääohjelma

def build(cfg=None):
    cfg = cfg or load_config()
    data = pipeline.load_data()
    ev = evaluate(cfg, data)
    hist = cycle_reference(ev)
    official, preview, daily = ev["official"], ev["preview"], ev["daily"]
    cur, prev = official[-1], (official[-2] if len(official) > 1 else None)

    # Nykyhinta: tuorein Bitstamp-sulku (voi olla kesken oleva päivä), muuten CoinMetrics
    ohlc = data.get("ohlc_daily")
    cm_last = daily.iloc[-1]
    if ohlc is not None and len(ohlc) and ohlc["date"].max() >= cm_last["date"]:
        price_now = {"price": float(ohlc.iloc[-1]["close"]), "date": ohlc.iloc[-1]["date"], "source": "Bitstamp"}
    else:
        price_now = {"price": float(cm_last["price"]), "date": cm_last["date"], "source": "CoinMetrics"}
    P = price_now["price"]

    sig_cur = signal_block(cur, cfg, hist, ev["cycles"], P)
    sig_prev_zones = scoring.zones(prev["row"], cfg, P) if prev else []
    change_list = ex.changes({**cur, "zones": sig_cur["zones"]},
                             {**prev, "zones": sig_prev_zones} if prev else None, cfg)
    summary = ex.summary(cur["row"], cur["scored"], cur["phase"], sig_cur["zones"], cfg, P)

    pv = None
    if preview:
        pv = {"week_start": preview["row"]["week_start"], "data_through": preview["row"]["date"],
              "close": preview["row"]["price"], "total": preview["scored"]["total"], "phase": preview["phase"],
              "phase_name": cfg["phases"]["names"][str(preview["phase"])],
              "layers": {k: preview["scored"]["layers"][k]["score"] for k in scoring.LAYERS}}

    # Fibonacci viimeisimmästä syklistä
    ic = cfg["indicators"]
    last_cycle = ev["cycles"][-1]
    fib = ind.fib_levels(last_cycle["bottom_price"], last_cycle["top_price"], ic["fib_retracements"],
                         ic["fib_extensions"], ic["fib_scale"])
    fib.update(low_date=last_cycle["bottom_date"], high_date=last_cycle["top_date"],
               top_confirmed=last_cycle["top_confirmed"])

    last_h = pd.Timestamp(cfg["halvings"][-1])
    halving = {"last": cfg["halvings"][-1], "days_since": int((pd.Timestamp(cm_last["date"]) - last_h).days),
               "next_estimate": (last_h + pd.Timedelta(days=cfg["halving_interval_days"])).strftime("%Y-%m-%d"),
               "next_is_estimate": True, "cycles": ev["cycles"]}

    status = load_status()
    now = datetime.now(timezone.utc)
    data_as_of = (pd.Timestamp(cm_last["date"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sources = {k: {"ok": v.get("ok"), "last_success": v.get("last_success"), "last_date": v.get("last_date"),
                   "error": v.get("error")} for k, v in status.items()}

    latest = {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_as_of": data_as_of,
        "stale_hours": cfg["data"]["stale_hours"],
        "sources": sources,
        "price_now": price_now,
        "signal": sig_cur,
        "summary": summary,
        "changes": change_list,
        "preview": pv,
        "fib": fib,
        "halving": halving,
        "cycle_reference": hist,
        "info": ex.info(cfg),
        "phase_names": cfg["phases"]["names"],
        "phase_actions": {str(k): v for k, v in ex.PHASE_ACTIONS.items()},
    }

    # ---- historia ja kaaviodata
    start = pd.Timestamp(cfg["backtest"]["start"])
    weeks, transitions, prev_phase = [], [], None
    for it in official:
        r = it["row"]
        if it["phase"] != prev_phase and prev_phase is not None and r["week_start"] >= start:
            transitions.append({"week_start": r["week_start"], "from": prev_phase, "to": it["phase"],
                                "price": r["price"], "total": it["scored"]["total"]})
        prev_phase = it["phase"]
        if r["week_start"] < start:
            continue
        L = it["scored"]["layers"]
        weeks.append({"t": ts(r["week_start"]), "c": sig(r["price"]), "s": sig(it["scored"]["total"], 4),
                      "p": it["phase"], "l": [sig(L[k]["score"], 4) for k in scoring.LAYERS]})

    candles = []
    if ohlc is not None and len(ohlc):
        wo = ind.to_weekly_ohlc(ohlc)
        candles = [[ts(x.week_start), sig(x.open), sig(x.high), sig(x.low), sig(x.close), bool(x.complete)]
                   for x in wo.itertuples()]

    w = ev["weekly"]
    zc = cfg["zones"]
    line_series = {"sma200w": w["sma200w"], "sma20w": w["sma20w"], "ema21w": w["ema21w"], "sma50w": w["sma50w"],
                   "realized_price": w["realized_price"], "pi_upper": w["pi_upper"]}
    for b in zc["buy"]:
        if b["type"] == "wma200":
            line_series[b["id"]] = w["sma200w"] * b.get("mult", 1.0)
        else:
            line_series[b["id"]] = w["realized_price"]
    zscale = w.apply(lambda row: scoring.zone_z_scale(row.to_dict(), cfg), axis=1)
    for s in zc["sell"]:
        line_series[s["id"]] = ind.mvrv_z_price(w["realized_cap"], w["sigma"], w["supply"], s["z"] * zscale)
    lines = {"t": [ts(x) for x in w["week_start"]]}
    lines.update({k: [sig(v) for v in s] for k, s in line_series.items()})

    # syklivertailu: hinta / hinta halvingpäivänä, viikon välein
    px = daily.set_index("date")["price"]
    cycle_series = []
    for h in cfg["halvings"]:
        h = pd.Timestamp(h)
        if h not in px.index:
            continue
        seg = px[(px.index >= h) & (px.index <= h + pd.Timedelta(days=cfg["halving_interval_days"]))]
        seg = seg.iloc[::7]
        cycle_series.append({"halving": h.strftime("%Y-%m-%d"), "base_price": float(px[h]),
                             "days": [int((d - h).days) for d in seg.index], "ratio": [sig(v / px[h], 5) for v in seg]})

    history = {
        "generated_at": latest["generated_at"],
        "layer_order": scoring.LAYERS,
        "weeks": weeks,
        "transitions": transitions,
        "candles": candles,
        "lines": lines,
        "cycles": cycle_series,
        "divergences": ev["div_events"],
        "zone_ids": {"buy": [b["id"] for b in zc["buy"]], "sell": [s["id"] for s in zc["sell"]]},
    }

    SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SITE_DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(jsonable(latest), f, ensure_ascii=False, indent=1)
    with open(SITE_DATA_DIR / "history.json", "w", encoding="utf-8") as f:
        json.dump(jsonable(history), f, ensure_ascii=False, separators=(",", ":"))
    return latest, history


if __name__ == "__main__":
    latest, history = build()
    s = latest["signal"]
    print(f"Viikko {str(s['week_start'])[:10]}: {s['phase_name']}, piste {s['total']:.1f}")
    print(latest["summary"])
    for c in latest["changes"]:
        print(" -", c)
    print(f"history: {len(history['weeks'])} viikkoa, {len(history['candles'])} kynttilää")
