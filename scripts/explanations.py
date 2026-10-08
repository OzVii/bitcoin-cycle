"""Rule-based English explanations for the site. Deterministic: same input → same text."""
import calendar
import math

import pandas as pd


# ---------------------------------------------------------------- formatting

def _nan(x):
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def fnum(x, dec=1):
    return "–" if _nan(x) else f"{x:,.{dec}f}"


def fusd(x):
    return "–" if _nan(x) else f"${fnum(x, 0)}"


def fpct(x, dec=1, sign=True):
    if _nan(x):
        return "–"
    pre = ("+" if x > 0 else "−" if x < 0 else "") if sign else ("−" if x < 0 else "")
    return f"{pre}{fnum(abs(x), dec)}%"


def fscore(x):
    if _nan(x):
        return "–"
    v = round(x)
    return f"+{v}" if v > 0 else (f"−{abs(v)}" if v < 0 else "0")


def hist_range(items, key, dec=1):
    vals = [(i["year"], i.get(key)) for i in items if not _nan(i.get(key))]
    if not vals:
        return None
    lo, hi = min(v for _, v in vals), max(v for _, v in vals)
    years = ", ".join(str(y) for y, _ in vals)
    rng = fnum(lo, dec) if len(vals) == 1 else f"{fnum(lo, dec)}–{fnum(hi, dec)}"
    return f"{rng} ({years})"


def fng_class(v):
    if _nan(v):
        return "–"
    if v < 25:
        return "extreme fear"
    if v < 45:
        return "fear"
    if v <= 55:
        return "neutral"
    if v <= 75:
        return "greed"
    return "extreme greed"


def effect_sentence(layer):
    s, w = layer["score"], layer["weight"]
    if _nan(s):
        return "No data is available for this period, so the layer's weight is shared among the other layers."
    lead = "favours buying" if s > 10 else "favours selling" if s < -10 else "is neutral"
    return (f"Layer score {fscore(s)} {lead}; at {fnum(w * 100, 0)}% weight it adds "
            f"{fscore(s * w)} to the total score.")


# ---------------------------------------------------------------- phases

PHASE_ACTIONS = {
    1: "Buy zone. Valuation is very low but the trend has not turned yet. Accumulate in steps and wait for the trend to confirm.",
    2: "Strongest buy setup: valuation is still moderate and the trend has turned up.",
    3: "Hold. Valuation is moderate and the trend is up.",
    4: "Sell zone, scale out in steps. Valuation is high and the market is overheated.",
    5: "Wait. The trend has turned down from a high level.",
}

LAYER_NAMES = {"valuation": "Valuation & cycle", "trend": "Trend", "momentum": "Momentum",
               "sentiment": "Sentiment", "macro": "Macro"}


def valuation_level(s):
    if _nan(s):
        return "not available"
    if s >= 60:
        return "historically low"
    if s >= 20:
        return "fairly low"
    if s > -20:
        return "neutral"
    if s > -60:
        return "elevated but not overheated"
    return "overheated"


# ---------------------------------------------------------------- layers

def text_valuation(r, layer, hist):
    parts = []
    if not _nan(r.get("wma200_mult")):
        s = f"Price is {fnum(r['wma200_mult'], 2)}× the 200-week average."
        t = hist_range(hist["tops"], "wma200_mult", 1)
        if t:
            s += f" At previous cycle tops the multiple was {t}"
            b = hist_range(hist["bottoms"], "wma200_mult", 2)
            s += f" and at bottoms {b}." if b else "."
        parts.append(s)
    if not _nan(r.get("mvrv_z")):
        s = f"MVRV Z-score is {fnum(r['mvrv_z'], 2)}"
        t = hist_range(hist["tops"], "mvrv_z", 1)
        s += f"; at tops it has been {t}." if t else "."
        parts.append(s)
    dz, dw = layer.get("decay", {}).get("mvrv_z"), layer.get("decay", {}).get("wma200")
    bits = []
    if dz and dz["scale"] < 1.0:
        bits.append(f"MVRV Z {fnum(dz['anchor_x'], 2)} (previous period peak {fnum(dz['ref'], 1)})")
    if dw and dw["scale"] < 1.0:
        bits.append(f"200W multiple {fnum(dw['anchor_x'], 2)} (previous period peak {fnum(dw['ref'], 1)})")
    if bits:
        parts.append("Cycles have weakened, so sell thresholds are scaled to the previous halving period's peaks; "
                     "the −60 point mark is now at " + " and ".join(bits) + ".")
    if not _nan(r.get("puell")):
        parts.append(f"Puell Multiple is {fnum(r['puell'], 2)}.")
    pi_w = r.get("pi_cross_weeks_ago")
    if not _nan(pi_w) and pi_w < 8:
        parts.append(f"The Pi Cycle cross happened {fnum(pi_w, 0)} weeks ago; historically it has landed near cycle tops.")
    elif not _nan(r.get("pi_dist_pct")):
        d = r["pi_dist_pct"]
        if d > 0:
            parts.append(f"Pi Cycle: the 111-day average would have to rise {fpct(d, 0, sign=False)} to trigger the top signal.")
        else:
            parts.append("Pi Cycle: the 111-day average is above the cross line.")
    parts.append(f"Valuation is {valuation_level(layer['score'])}.")
    parts.append(effect_sentence(layer))
    return " ".join(parts)


def text_trend(r, layer, cfg):
    parts = []
    st, n, trend = r.get("band_state"), r.get("band_streak"), r.get("trend")
    if _nan(st):
        return "Not enough trend data yet. " + effect_sentence(layer)
    band = f"{fusd(r.get('band_bottom'))}–{fusd(r.get('band_top'))}"
    where = {"above": "above", "below": "below", "inside": "inside"}[st]
    weeks = "week" if n == 1 else "consecutive weeks"
    parts.append(f"The weekly close ({fusd(r['price'])}) has been {where} the bull market support band ({band}) for {n} {weeks}.")
    need = cfg["indicators"]["trend_confirm_weeks"]
    if trend == "up":
        parts.append("The uptrend is confirmed." if st == "above"
                     else "The last confirmed direction is up, but the close is no longer above the band.")
    elif trend == "down":
        parts.append("The downtrend is confirmed." if st == "below"
                     else "The last confirmed direction is down, but the close is no longer below the band.")
    if st in ("above", "below") and n < need:
        parts.append(f"A change of direction needs {need} consecutive weekly closes to confirm.")
    sl = r.get("sma50w_slope")
    if not _nan(sl):
        wk = cfg["indicators"]["sma50w_slope_weeks"]
        verb = "is rising" if sl > 0.5 else "is falling" if sl < -0.5 else "is roughly flat"
        parts.append(f"The 50-week SMA ({fusd(r.get('sma50w'))}) {verb} ({fpct(sl)} over {wk} weeks).")
    parts.append(effect_sentence(layer))
    return " ".join(parts)


def text_momentum(r, layer, hist):
    parts = []
    rw, rm = r.get("rsi_w"), r.get("rsi_m")
    s = f"Weekly RSI is {fnum(rw, 0)} and monthly RSI {fnum(rm, 0)}."
    if not _nan(rw):
        if rw >= 80:
            s += " Weekly RSI is overbought."
        elif rw <= 30:
            s += " Weekly RSI is oversold."
    t = hist_range(hist["tops"], "rsi_w", 0)
    if t:
        s += f" At cycle tops weekly RSI has been {t}."
    parts.append(s)
    h, hp = r.get("macd_hist_m"), r.get("macd_hist_prev_m")
    if not _nan(h):
        sign = "positive" if h > 0 else "negative"
        trend = ""
        if not _nan(hp):
            if (h > 0) != (hp > 0):
                trend = " and just changed sign"
            else:
                trend = " and strengthening" if abs(h) > abs(hp) else " and weakening"
        parts.append(f"The monthly MACD histogram is {sign}{trend} (shown for information, not scored).")
    if r.get("div_bear"):
        parts.append("Weekly RSI shows a fresh bearish divergence: price made a higher high while RSI made a lower high.")
    if r.get("div_bull"):
        parts.append("Weekly RSI shows a fresh bullish divergence: price made a lower low while RSI made a higher low.")
    parts.append(effect_sentence(layer))
    return " ".join(parts)


def text_sentiment(r, layer):
    f, a = r.get("fng"), r.get("fng_avg")
    if _nan(a):
        return "Fear & Greed history starts in February 2018. " + effect_sentence(layer)
    parts = [f"Fear & Greed is {fnum(f, 0)} ({fng_class(f)}), 4-week average {fnum(a, 0)} ({fng_class(a)})."]
    if a >= 75:
        parts.append("Sustained greed has historically gone together with an overheated market.")
    elif a <= 25:
        parts.append("Sustained fear has historically been close to cycle bottoms.")
    parts.append(effect_sentence(layer))
    return " ".join(parts)


def text_macro(r, layer):
    parts = []
    y, acc, mon = r.get("m2_yoy"), r.get("m2_accel"), r.get("m2_month")
    if not _nan(y):
        mname = f" ({calendar.month_name[mon.month]} {mon.year})" if not _nan(mon) else ""
        dirn = "accelerating" if acc > 0.2 else "slowing" if acc < -0.2 else "steady"
        parts.append(f"US M2 money supply is growing {fpct(y, 1, sign=False)} year on year{mname}, and growth is {dirn} "
                     f"({fnum(acc, 1)} pp over 3 months).")
    d = r.get("dollar_13w_pct")
    if not _nan(d):
        verb = "weakened" if d < 0 else "strengthened"
        parts.append(f"The broad dollar index has {verb} {fpct(abs(d), 1, sign=False)} over 13 weeks.")
    s = layer["score"]
    if not _nan(s):
        if s > 20:
            parts.append("Liquidity conditions support risk assets.")
        elif s < -20:
            parts.append("Liquidity conditions are tightening.")
        else:
            parts.append("Liquidity conditions are neutral.")
    parts.append(effect_sentence(layer))
    return " ".join(parts)


def cycle_timing_text(days, last_halving, cycles):
    """Time since halving compared with the timing of earlier tops and bottoms."""
    if _nan(days):
        return ""
    done = [c for c in cycles if c["top_confirmed"] and c["halving"] != last_halving]
    s = f"{fnum(days, 0)} days have passed since the last halving."
    if done:
        tops = [c["top_days_after_halving"] for c in done]
        s += f" In earlier cycles the top came {min(tops)}–{max(tops)} days after the halving"
        bots = [c["next_bottom_days_after_halving"] for c in done if "next_bottom_days_after_halving" in c]
        s += f" and the bottom {min(bots)}–{max(bots)} days after." if bots else "."
        if bots and max(tops) < days < min(bots):
            s += " In time, the cycle is past the earlier tops, in what has typically been a declining phase."
        elif bots and days >= min(bots):
            s += " In time, we are in or past the window of earlier cycle bottoms."
        elif days < min(tops):
            s += " In time, the cycle is still before the window of earlier tops."
        else:
            s += " In time, we are in the window of earlier tops."
    return s


def layer_texts(r, scored, hist, cfg):
    L = scored["layers"]
    return {
        "valuation": text_valuation(r, L["valuation"], hist),
        "trend": text_trend(r, L["trend"], cfg),
        "momentum": text_momentum(r, L["momentum"], hist),
        "sentiment": text_sentiment(r, L["sentiment"]),
        "macro": text_macro(r, L["macro"]),
    }


# ---------------------------------------------------------------- summary

def summary(r, scored, phase, zones, cfg, current_price):
    L = scored["layers"]
    s1 = f"Total score {fscore(scored['total'])}. {PHASE_ACTIONS[phase]}"

    contrib = sorted(((k, L[k]["score"] * L[k]["weight"]) for k in L if not _nan(L[k]["score"])),
                     key=lambda kv: -abs(kv[1]))[:2]
    reasons = []
    for k, c in contrib:
        tone = "favours buying" if c > 0 else "favours selling" if c < 0 else "is neutral"
        detail = ""
        if k == "valuation":
            detail = f" (MVRV Z {fnum(r.get('mvrv_z'), 1)}, 200W multiple {fnum(r.get('wma200_mult'), 2)})"
        elif k == "trend":
            detail = {"up": " (uptrend confirmed)", "down": " (downtrend confirmed)"}.get(r.get("trend"), "")
        elif k == "sentiment":
            detail = f" (Fear & Greed {fnum(r.get('fng_avg'), 0)})"
        elif k == "momentum":
            detail = f" (weekly RSI {fnum(r.get('rsi_w'), 0)})"
        reasons.append(f"{LAYER_NAMES[k].lower()}{detail} {tone}")
    s2 = ("Main drivers: " + " and ".join(reasons) + ".") if reasons else ""

    buys = [z for z in zones if z["kind"] == "buy"]
    sells = [z for z in zones if z["kind"] == "sell" and z["id"].startswith("sell")]
    if phase == 1:
        s3 = f"Watch for two consecutive weekly closes above the support band ({fusd(r.get('band_top'))})."
    elif phase in (2, 3):
        nxt = min((z for z in sells if z["price"] > current_price), key=lambda z: z["price"], default=None)
        s3 = f"Watch whether the weekly close holds above the lower edge of the support band ({fusd(r.get('band_bottom'))})."
        if nxt:
            s3 += f" The nearest sell level, {nxt['name']}, is {fpct(nxt['distance_pct'], 0)} away."
    elif phase == 4:
        s3 = (f"Watch for bearish divergences and the weekly close against the lower edge of the support band "
              f"({fusd(r.get('band_bottom'))}); a close below it would confirm the turn.")
    else:
        nxt = max((z for z in buys if z["price"] < current_price), key=lambda z: z["price"], default=None)
        s3 = (f"Watch the price approach the buy zones: {nxt['name']} is {fpct(nxt['distance_pct'], 0)} away."
              if nxt else "Price is already in the buy zones; watch for the trend to turn.")
    return " ".join(x for x in (s1, s2, s3) if x)


# ---------------------------------------------------------------- changes

def changes(cur, prev, cfg):
    """cur/prev = {'row', 'scored', 'phase', 'zones'} for two consecutive closed weeks."""
    if prev is None:
        return []
    names = cfg["phases"]["names"]
    out = []
    if cur["phase"] != prev["phase"]:
        out.append(f"Phase changed: {names[str(prev['phase'])]} → {names[str(cur['phase'])]}.")
    pc, cc = prev["row"]["price"], cur["row"]["price"]
    prev_z = {z["id"]: z for z in prev["zones"]}
    for z in cur["zones"]:
        pz = prev_z.get(z["id"])
        if not pz:
            continue
        if pc >= pz["price"] and cc < z["price"]:
            out.append(f"The weekly close fell below {z['name']} ({fusd(z['price'])}).")
        elif pc < pz["price"] and cc >= z["price"]:
            out.append(f"The weekly close rose above {z['name']} ({fusd(z['price'])}).")
    if cur["row"].get("trend") != prev["row"].get("trend") and cur["row"].get("trend"):
        out.append("The trend was confirmed up." if cur["row"]["trend"] == "up" else "The trend was confirmed down.")
    if cur["row"].get("div_bear") and not prev["row"].get("div_bear"):
        out.append("A new bearish RSI divergence was confirmed.")
    if cur["row"].get("div_bull") and not prev["row"].get("div_bull"):
        out.append("A new bullish RSI divergence was confirmed.")
    for k, L in cur["scored"]["layers"].items():
        a, b = L["score"], prev["scored"]["layers"][k]["score"]
        if not _nan(a) and not _nan(b) and abs(a - b) >= 20:
            out.append(f"{LAYER_NAMES[k]} layer score moved {fscore(b)} → {fscore(a)}.")
    return out


# ---------------------------------------------------------------- help popups

def info(cfg):
    """Help texts for the popups. Each entry: title + body (paragraphs; a list item = bullet list).
    Thresholds come from config, so the texts stay in sync when parameters are tuned."""
    p = cfg["phases"]
    w = cfg["scoring"]["layer_weights"]
    names = p["names"]
    dc = cfg["scoring"]["valuation"].get("cycle_decay", {})
    pct = lambda k: f"{round(w[k] * 100)}%"
    return {
        # ---- sections
        "score": {"title": "Cycle gauge and total score", "body": [
            "The gauge shows the total score from −100 to +100. +100 means the indicators strongly favour buying, −100 that they strongly favour selling.",
            "The total is a weighted sum of five layers:",
            [f"Valuation & cycle {pct('valuation')}", f"Trend {pct('trend')}", f"Momentum {pct('momentum')}",
             f"Sentiment {pct('sentiment')}", f"Macro {pct('macro')}"],
            "If a layer has no data for a period (for example Fear & Greed before 2018), its weight is shared among the others.",
            "The score uses only closed weekly candles (Monday–Sunday, UTC). The running week is shown separately as a preview.",
        ]},
        "phase": {"title": "Market phases", "body": [
            "The phase is derived from the valuation layer score, the confirmed trend and, for overheating, the total score and sentiment.",
            [
                f"1 {names['1']}: valuation score ≥ {p['bottom_min_valuation']} and the trend is not yet confirmed up. Accumulate in steps.",
                f"2 {names['2']}: trend confirmed up and valuation score ≥ {p['early_min_valuation']}. Historically the strongest buy setup.",
                f"3 {names['3']}: trend up, valuation moderate. Hold.",
                f"4 {names['4']}: valuation score ≤ {p['overheat_max_valuation']}, or total ≤ {p['overheat_max_total']}, or valuation ≤ {p['overheat_soft_max_valuation']} together with greed (F&G ≥ {p['overheat_fng_min']}) or a bearish divergence. Scale out in steps.",
                f"5 {names['5']}: trend confirmed down. Wait.",
            ],
            f"To stop the phase flipping back and forth at a boundary, a new phase must hold for {p['min_weeks_to_switch']} weeks and clear the boundary by more than {p['hysteresis_margin']} points (hysteresis).",
        ]},
        "preview": {"title": "Running week preview", "body": [
            "Shows what the score and phase would be if the current, unfinished week closed at the latest price.",
            "It does not affect the official signal, which only changes after the weekly close on Sunday 24:00 UTC. Intra-week moves often reverse, so treat it as a heads-up only.",
        ]},
        "changes": {"title": "Changes from last week", "body": [
            "Lists what changed between the two latest closed weeks: a phase change, the weekly close crossing a buy or sell level, a newly confirmed trend or divergence, or a layer score moving by 20 points or more.",
        ]},
        "zones": {"title": "Buy and sell zones", "body": [
            "Staggered price levels for scaling in and out. Each is shown as a ±" + str(cfg["zones"]["range_pct"]) + "% range together with its distance from the current price.",
            ["Buy 1: 200-week SMA × 1.3", "Buy 2: 200-week SMA", "Buy 3: realized price (the market's average cost basis)",
             "Sell 1–3: prices at which MVRV Z would reach 5, 6 and 7, scaled for weakening cycles",
             "Pi Cycle line: 2 × the 350-day SMA"],
            "The bar at the top places the current price (orange dot) between the buy zone (green) and the sell zone (red) on a log scale. The levels move over time as the averages move.",
        ]},
        "price_chart": {"title": "How to read the price chart", "body": [
            "Weekly candles on a log scale, so equal percentage moves look the same size. The orange candle is the running week.",
            ["Orange line: 200-week SMA, the long-term floor", "Blue lines: bull market support band (20W SMA solid, 21W EMA dashed)",
             "Purple line: 50-week SMA", "Green band: buy zone (Buy 1 – Buy 3)", "Red band: sell zone (Sell 1 – Sell 3)",
             "Grey dashed lines: Fibonacci levels of the last cycle (toggle)"],
            "Drag to pan, scroll or pinch to zoom.",
        ]},
        "cycles": {"title": "Cycle comparison", "body": [
            "Each line is one halving cycle: price divided by the price on halving day, plotted against days since the halving. The orange line is the current cycle, the dots mark each cycle's top.",
            "Each cycle has risen less than the previous one, so compare the shape and timing rather than the height. With only four cycles, the timing is a rough guide.",
        ]},
        "backtest": {"title": "Backtest", "body": [
            "The score and phase were computed week by week from 2014, each week using only data available at that time (no look-ahead). The background colour shows the phase.",
            "Top chart: weekly close (log scale). Bottom chart: total score; green above zero favours buying, red below zero favours selling.",
            "Caveat: there are only about four cycles, and the thresholds were chosen with them in view, so the past fit flatters the method. Bottoms have been identified well; recent tops (2021, 2025) were mostly caught by the trend turning down, not by valuation.",
        ]},
        "transitions": {"title": "Phase changes", "body": [
            "Every week the official phase changed, with the weekly close and total score at that time. Short-lived changes show where the rules were indecisive.",
        ]},
        # ---- layers
        "layer_valuation": {"title": "Valuation & cycle layer", "body": [
            "Is Bitcoin cheap or expensive compared with its own history? Combines MVRV Z-score, price relative to the 200-week SMA and Puell Multiple; the Pi Cycle indicator can only pull the score down.",
            "High score = cheap (favours buying), low score = expensive (favours selling). This layer has the largest weight because valuation has marked cycle bottoms reliably.",
        ]},
        "layer_trend": {"title": "Trend layer", "body": [
            "Which way is the long-term trend going? Based on the weekly close relative to the bull market support band and the slope of the 50-week SMA.",
            "A trend change needs two consecutive weekly closes on the new side of the band. An uptrend gives a positive score, a downtrend a negative one.",
        ]},
        "layer_momentum": {"title": "Momentum layer", "body": [
            "How strong are the recent moves? Uses weekly and monthly RSI: very high RSI (overbought) lowers the score, very low RSI (oversold) raises it.",
            "RSI divergences add or subtract points. Monthly MACD is shown for information only.",
        ]},
        "layer_sentiment": {"title": "Sentiment layer", "body": [
            "How do market participants feel? Uses the 4-week average of the Fear & Greed index. Fear raises the score, greed lowers it: the market has tended to bottom in fear and top in greed.",
        ]},
        "layer_macro": {"title": "Macro layer", "body": [
            "Is global liquidity helping or hurting? Accelerating US M2 money supply growth and a weakening dollar raise the score; the opposite lowers it.",
            "Macro has a small weight because its effect is slow and indirect.",
        ]},
        # ---- metrics
        "wma200": {"title": "Price / 200-week SMA", "body": [
            "The 200-week moving average is Bitcoin's long-term baseline. Price has only gone below it in the deepest bear markets, and the multiple (price ÷ 200W SMA) has reached several times its value at cycle tops.",
            "Low multiple = cheap, high multiple = expensive."]},
        "mvrv_z": {"title": "MVRV Z-score", "body": [
            "Compares market value with realized value (each coin valued at the price when it last moved) and scales the gap by the standard deviation of market value over the past 4 years.",
            "Below 0 has marked cycle bottoms; high readings have marked tops. Top readings have fallen each cycle, which is why sell thresholds are scaled down (see 'MVRV Z sell threshold')."]},
        "realized_price": {"title": "Realized price", "body": [
            "The average price at which all coins last moved: roughly the market's average cost basis. Below it, the average holder is at a loss, which has historically been a deep-value zone."]},
        "puell": {"title": "Puell Multiple", "body": [
            "Daily miner issuance in dollars divided by its 365-day average. Low values mean miners are under stress (historically near bottoms); high values mean exceptional miner income (near tops). Each halving pushes it down mechanically."]},
        "pi_cycle": {"title": "Pi Cycle Top", "body": [
            "When the 111-day SMA rises above 2 × the 350-day SMA, the market has historically been within days of a cycle top (2013, 2017, 2021). The distance shows how much the 111-day average would have to rise to cross.",
            "This indicator can only pull the valuation score down; it never adds buy points."]},
        "halving": {"title": "Halving", "body": [
            "The halving cuts new Bitcoin issuance in half roughly every four years. In earlier cycles the top came 12–18 months after the halving and the bottom about a year after the top. The sample is small, so treat timing as a rough guide.",
            "The next halving date is an estimate (previous + 4 years)."]},
        "support_band": {"title": "Bull market support band", "body": [
            "The 20-week SMA and 21-week EMA. In bull markets price tends to stay above the band and pullbacks stop at it; weekly closes below it have often signalled a trend change. Confirmation needs two consecutive weekly closes."]},
        "sma50w": {"title": "50-week SMA", "body": [
            "Describes the year-long trend. Its slope (change over 4 weeks) shows whether the long trend is rising or falling."]},
        "rsi": {"title": "RSI (14)", "body": [
            "Relative Strength Index measures the strength of gains versus losses on a 0–100 scale. On the weekly chart, readings above 80 have been typical near tops and below 30 near bottoms. Monthly RSI uses closed months only."]},
        "macd": {"title": "Monthly MACD", "body": [
            "MACD (12, 26, 9) on the monthly chart describes the direction of long-term momentum. A turn in the histogram is a slow but fairly reliable signal. Shown for information; not scored by default."]},
        "divergence": {"title": "RSI divergence", "body": [
            "A divergence is when price and RSI move apart. Bearish: price makes a higher high but RSI a lower high, meaning momentum is fading. Bullish: price makes a lower low but RSI a higher low.",
            "A pivot is only confirmed a couple of weeks after it forms, so the signal never uses future data."]},
        "fng": {"title": "Fear & Greed index", "body": [
            "alternative.me's index combines volatility, volume, social media and dominance into a single 0–100 reading. Extreme fear has often been a buying opportunity and extreme greed a selling one. The score uses the 4-week average."]},
        "m2": {"title": "M2 money supply", "body": [
            "The year-on-year change in US M2 is used as a proxy for global liquidity. Accelerating money supply growth has historically supported risk assets. The data is published with about a month's delay, and the calculation accounts for that."]},
        "dollar": {"title": "Dollar index", "body": [
            "The broad dollar index (FRED DTWEXBGS) measures the dollar against trading partners' currencies. A weakening dollar has usually been positive for Bitcoin. It is not exactly DXY but moves in the same direction."]},
        "fib": {"title": "Fibonacci levels", "body": [
            "Drawn from the last cycle's bottom to its top. Retracements (0.382–0.786) are possible support areas in a correction; extensions (1.618, 2.618) are possible future targets. Display only; they do not affect the score."]},
        "cycle_decay": {"title": "MVRV Z sell threshold", "body": [
            "Every cycle has topped at lower valuation readings (MVRV ratio at tops 4.7 → 4.4 → 3.4 → 2.3). So the sell-side thresholds are scaled to the previous halving period's peak: "
            f"the −60 point mark = {dc.get('reference_ratio', 0.6)} × that peak. The previous period is entirely in the past, so no future data is used. Buy-side thresholds do not change.",
            "The value shows the current threshold and the scale factor applied to the base threshold."]},
    }
