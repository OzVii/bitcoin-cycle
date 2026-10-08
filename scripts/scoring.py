"""Alipisteet (−100 … +100, + = ostoa puoltava), kerrokset, kokonaispiste, vaiheet ja alueet."""
import math

import indicators as ind

LAYERS = ["valuation", "trend", "momentum", "sentiment", "macro"]


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def clamp(x, lo=-100.0, hi=100.0):
    return x if _nan(x) else max(lo, min(hi, x))


def piecewise(x, points):
    """Paloittain lineaarinen muunnos. points = [[x, pistettä], ...] nousevassa x-järjestyksessä.
    Sama x kahdesti = porras: x täsmälleen rajalla saa ensimmäisen arvon. Päiden ulkopuolella vakio."""
    if _nan(x):
        return float("nan")
    x = float(x)
    if x <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 < x <= x1:
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    return float(points[-1][1])


def inverse_piecewise(points, score):
    """Ensimmäinen x, jossa laskeva paloittain lineaarinen funktio saavuttaa annetun pisteen."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 != y1 and min(y0, y1) <= score <= max(y0, y1):
            return x0 + (score - y0) * (x1 - x0) / (y1 - y0)
    return float("nan")


def decay_scale(points, ref, dc):
    """Skaalauskerroin myyntipuolen kynnyksille edellisen syklin huippuarvon perusteella."""
    if not dc.get("enabled") or _nan(ref):
        return 1.0
    anchor_x = inverse_piecewise(points, dc["anchor_score"])
    if _nan(anchor_x) or anchor_x <= 0:
        return 1.0
    s = dc["reference_ratio"] * ref / anchor_x
    return max(dc["min_scale"], min(dc["max_scale"], s))


def scale_sell_points(points, s):
    """Kertoo myyntipuolen (piste < 0) x-arvot s:llä; järjestys säilyy aina nousevana."""
    if s == 1.0:
        return points
    out, prev_x = [], None
    for x, y in points:
        if y < 0:
            x = x * s
            if prev_x is not None and x <= prev_x:
                x = prev_x + 0.01
        out.append([x, y])
        prev_x = x
    return out


def decayed_points(r, cfg, key):
    """Palauttaa (pisteytyspisteet, skaala, referenssi) mittarille key ("mvrv_z" / "wma200")."""
    v = cfg["scoring"]["valuation"]
    dc = v.get("cycle_decay", {})
    col = dc.get("metrics", {}).get(key)
    if not col:
        return v[key], 1.0, float("nan")
    ref = r.get(f"ref_{col}")
    s = decay_scale(v[key], ref, dc)
    return scale_sell_points(v[key], s), s, ref


def weighted_avg(scores, weights):
    """Painotettu keskiarvo; puuttuvan osan paino jaetaan muille suhteessa."""
    tot = sum(weights[k] for k, v in scores.items() if not _nan(v) and weights.get(k, 0) > 0)
    if tot == 0:
        return float("nan"), {}
    eff = {k: weights[k] / tot for k, v in scores.items() if not _nan(v) and weights.get(k, 0) > 0}
    return sum(scores[k] * w for k, w in eff.items()), eff


def score_row(r, cfg):
    """r = viikkorivi (dict). Palauttaa komponenttien ja kerrosten pisteet."""
    sc = cfg["scoring"]
    out = {}

    # --- arvostus ja sykli
    v = sc["valuation"]
    z_pts, z_s, z_ref = decayed_points(r, cfg, "mvrv_z")
    w_pts, w_s, w_ref = decayed_points(r, cfg, "wma200")
    comp = {
        "mvrv_z": piecewise(r.get("mvrv_z"), z_pts),
        "wma200": piecewise(r.get("wma200_mult"), w_pts),
        "puell": piecewise(r.get("puell"), v["puell"]),
    }
    anchor = v.get("cycle_decay", {}).get("anchor_score", -60)
    decay = {"mvrv_z": {"scale": z_s, "ref": z_ref, "anchor_x": inverse_piecewise(z_pts, anchor)},
             "wma200": {"scale": w_s, "ref": w_ref, "anchor_x": inverse_piecewise(w_pts, anchor)}}
    if not _nan(r.get("pi_cross_weeks_ago")) and r["pi_cross_weeks_ago"] < v["pi_cycle_cross_weeks"]:
        pi = float(v["pi_cycle_cross_score"])
    else:
        pi = piecewise(r.get("pi_dist_pct"), v["pi_cycle_distance_pct"])
    comp["pi_cycle"] = pi
    if v["pi_cycle_mode"] == "avg":
        val, _ = weighted_avg(comp, {**v["weights"], "pi_cycle": v["pi_cycle_weight"]})
    else:
        val, _ = weighted_avg({k: comp[k] for k in v["weights"]}, v["weights"])
        if not _nan(val) and not _nan(pi) and pi < 0:
            val = min(val, pi)
    out["valuation"] = {"score": clamp(val), "components": comp, "decay": decay}

    # --- trendi
    t = sc["trend"]
    trend = r.get("trend")
    if trend in ("up", "down"):
        sign = 1 if trend == "up" else -1
        base = t["band_score"] * sign
        matches = (trend == "up" and r.get("band_state") == "above") or \
                  (trend == "down" and r.get("band_state") == "below")
        if not matches:
            base *= t["inside_band_factor"]
        slope = piecewise(r.get("sma50w_slope"), t["slope_pct"])
        trend_score = clamp(base + (0 if _nan(slope) else slope))
    else:
        base, slope, trend_score = float("nan"), piecewise(r.get("sma50w_slope"), t["slope_pct"]), float("nan")
    out["trend"] = {"score": trend_score, "components": {"band": base, "slope": slope}}

    # --- momentum
    m = sc["momentum"]
    mc = {"rsi_weekly": piecewise(r.get("rsi_w"), m["rsi_weekly"]),
          "rsi_monthly": piecewise(r.get("rsi_m"), m["rsi_monthly"])}
    mom, _ = weighted_avg(mc, m["weights"])
    div = 0.0
    if r.get("div_bull"):
        div += m["divergence_score"]
    if r.get("div_bear"):
        div -= m["divergence_score"]
    mc["divergence"] = div
    out["momentum"] = {"score": clamp(mom + div) if not _nan(mom) else float("nan"), "components": mc}

    # --- sentimentti
    s = sc["sentiment"]
    f = r.get("fng_avg") if s["use"] == "avg4w" else r.get("fng")
    out["sentiment"] = {"score": piecewise(f, s["fng"]), "components": {"fng": piecewise(f, s["fng"])}}

    # --- makro
    mk = sc["macro"]
    m2s = piecewise(r.get("m2_accel"), mk["m2_accel_pp"])
    dls = piecewise(r.get("dollar_13w_pct"), mk["dollar_13w_pct"])
    if _nan(m2s) and _nan(dls):
        macro = float("nan")
    else:
        macro = clamp((0 if _nan(m2s) else m2s) + (0 if _nan(dls) else dls))
    out["macro"] = {"score": macro, "components": {"m2": m2s, "dollar": dls}}

    total, eff = weighted_avg({k: out[k]["score"] for k in LAYERS}, sc["layer_weights"])
    for k in LAYERS:
        out[k]["weight"] = eff.get(k, 0.0)
    return {"layers": out, "total": clamp(total)}


# ---------------------------------------------------------------- vaiheet

def classify(V, S, trend, fng_avg, bear_div, cfg, shift=0.0):
    """Ehdokasvaihe yhdelle viikolle. V = arvostuskerroksen piste, S = kokonaispiste.
    shift siirtää pisteitä hystereesitarkastelua varten. None = ei selvää ehdokasta."""
    p = cfg["phases"]
    if _nan(V):
        return None
    V = V + shift
    S = S + shift if not _nan(S) else S
    hot_sentiment = not _nan(fng_avg) and fng_avg >= p["overheat_fng_min"]
    if V >= p["bottom_min_valuation"] and trend != "up":
        return 1
    if trend == "up" and V >= p["early_min_valuation"]:
        return 2
    if V <= p["overheat_max_valuation"] or (not _nan(S) and S <= p["overheat_max_total"]) or \
            (V <= p["overheat_soft_max_valuation"] and (hot_sentiment or bear_div)):
        return 4
    if trend == "up":
        return 3
    if trend == "down":
        return 5
    if V >= p["early_min_valuation"]:
        return 1
    return None


class PhaseTracker:
    """Tilakone: vaihe vaihtuu vasta, kun uusi ehdokas on pysynyt min_weeks_to_switch viikkoa
    eikä nykyinen vaihe pysy voimassa ±hystereesimarginaalilla."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.phase = None
        self.pending = None
        self.pending_n = 0

    def copy(self):
        t = PhaseTracker(self.cfg)
        t.phase, t.pending, t.pending_n = self.phase, self.pending, self.pending_n
        return t

    def step(self, V, S, trend, fng_avg, bear_div):
        p = self.cfg["phases"]
        cand = classify(V, S, trend, fng_avg, bear_div, self.cfg)
        if self.phase is None:
            self.phase = cand
            return self.phase, cand
        if cand is None or cand == self.phase:
            self.pending, self.pending_n = None, 0
            return self.phase, cand
        h = p["hysteresis_margin"]
        holds = any(classify(V, S, trend, fng_avg, bear_div, self.cfg, shift=s) == self.phase for s in (-h, h))
        if holds:
            self.pending, self.pending_n = None, 0
            return self.phase, cand
        if cand == self.pending:
            self.pending_n += 1
        else:
            self.pending, self.pending_n = cand, 1
        if self.pending_n >= p["min_weeks_to_switch"]:
            self.phase, self.pending, self.pending_n = cand, None, 0
        return self.phase, cand


# ---------------------------------------------------------------- alueet

def zone_z_scale(r, cfg):
    """MVRV Z -myyntitasojen skaala (sama kuin pisteytyksessä, jos apply_to_zones)."""
    dc = cfg["scoring"]["valuation"].get("cycle_decay", {})
    if not dc.get("apply_to_zones"):
        return 1.0
    return decayed_points(r, cfg, "mvrv_z")[1]


def zones(r, cfg, current_price):
    z = cfg["zones"]
    rp = z["range_pct"] / 100
    out = []

    def add(item, kind, level, desc):
        if _nan(level):
            return
        out.append({"id": item["id"], "name": item["name"], "kind": kind, "price": level,
                    "low": level * (1 - rp), "high": level * (1 + rp), "basis": desc,
                    "distance_pct": (level / current_price - 1) * 100})

    for b in z["buy"]:
        if b["type"] == "wma200":
            mult = b.get("mult", 1.0)
            add(b, "buy", r["sma200w"] * mult,
                "200-week SMA" if mult == 1 else f"200-week SMA × {mult:.2f}")
        elif b["type"] == "realized_price":
            add(b, "buy", r["realized_price"], "Realized price")
    zs = zone_z_scale(r, cfg)
    for s in z["sell"]:
        zz = s["z"] * zs
        lvl = ind.mvrv_z_price(r["realized_cap"], r["sigma"], r["supply"], zz)
        desc = f"MVRV Z = {s['z']}" if zs == 1.0 else f"MVRV Z = {zz:.2f} (base {s['z']} × {zs:.2f})"
        add(s, "sell", lvl, desc)
    if z.get("show_pi_cycle"):
        add({"id": "pi", "name": "Pi Cycle line"}, "sell", r["pi_upper"], "2 × 350-day SMA")
    return out
