import copy
import math

import pandas as pd
import pytest

import scoring
from build import evaluate
from conftest import synthetic_data


def test_piecewise_interpolation_and_clamping():
    pts = [[0, 100], [2, 20], [5, -60], [7, -100]]
    assert scoring.piecewise(-1, pts) == 100
    assert scoring.piecewise(1, pts) == pytest.approx(60)
    assert scoring.piecewise(6, pts) == pytest.approx(-80)
    assert scoring.piecewise(10, pts) == -100
    assert math.isnan(scoring.piecewise(float("nan"), pts))


def test_piecewise_step():
    pts = [[1.0, 100], [1.0, 80], [1.5, 20]]
    assert scoring.piecewise(1.0, pts) == 100
    assert scoring.piecewise(1.0001, pts) == pytest.approx(80, abs=0.1)
    assert scoring.piecewise(1.25, pts) == pytest.approx(50)


def test_weight_redistribution():
    total, eff = scoring.weighted_avg({"a": 100, "b": float("nan"), "c": 0},
                                      {"a": 0.4, "b": 0.1, "c": 0.4})
    assert total == pytest.approx(50)
    assert eff == {"a": pytest.approx(0.5), "c": pytest.approx(0.5)}


def test_cycle_decay_scales_only_sell_side(cfg):
    dc = cfg["scoring"]["valuation"]["cycle_decay"]
    pts = [[0, 100], [2, 20], [5, -60], [7, -100]]
    s = scoring.decay_scale(pts, 4.0, dc)  # −60 raja → 0,6 × 4,0 = 2,4
    assert s == pytest.approx(2.4 / 5)
    scaled = scoring.scale_sell_points(pts, s)
    assert scaled[:2] == pts[:2]
    assert scoring.inverse_piecewise(scaled, -60) == pytest.approx(2.4)
    # kynnyksiä ei koskaan nosteta eikä lasketa alle min_scale
    assert scoring.decay_scale(pts, 100.0, dc) == 1.0
    assert scoring.decay_scale(pts, 0.1, dc) == dc["min_scale"]
    assert scoring.decay_scale(pts, float("nan"), dc) == 1.0


def test_scale_sell_points_keeps_order():
    pts = [[1.0, 100], [1.0, 80], [1.5, 20], [3.0, -40], [5.0, -100]]
    out = scoring.scale_sell_points(pts, 0.3)
    xs = [p[0] for p in out]
    assert xs == sorted(xs) and out[3][0] > 1.5


def test_pi_cycle_cap(cfg):
    r = {"mvrv_z": -1, "wma200_mult": 0.9, "puell": 0.3, "pi_dist_pct": 3, "pi_cross_weeks_ago": float("nan")}
    out = scoring.score_row(r, cfg)
    assert out["layers"]["valuation"]["score"] == -70
    r["pi_cross_weeks_ago"] = 2
    assert scoring.score_row(r, cfg)["layers"]["valuation"]["score"] == -100
    r.update(pi_dist_pct=50, pi_cross_weeks_ago=20)
    assert scoring.score_row(r, cfg)["layers"]["valuation"]["score"] == 100


def test_phase_switch_needs_persistence(cfg):
    c = copy.deepcopy(cfg)
    c["phases"]["min_weeks_to_switch"] = 2
    t = scoring.PhaseTracker(c)
    assert t.step(30, 20, "up", 50, False)[0] == 2
    # yksi viikko laskutrendiä ei vielä vaihda vaihetta
    assert t.step(0, 0, "down", 50, False)[0] == 2
    assert t.step(0, 0, "down", 50, False)[0] == 5


def test_phase_hysteresis_margin(cfg):
    c = copy.deepcopy(cfg)
    c["phases"]["min_weeks_to_switch"] = 1
    t = scoring.PhaseTracker(c)
    assert t.step(30, 20, "up", 50, False)[0] == 2
    # 20 < early_min_valuation (25), mutta marginaalin (10) sisällä → pysyy
    assert t.step(20, 10, "up", 50, False)[0] == 2
    assert t.step(10, 5, "up", 50, False)[0] == 3


def _official_frame(ev):
    return pd.DataFrame([{"week": it["row"]["week_start"], "total": it["scored"]["total"], "phase": it["phase"]}
                         for it in ev["official"]])


def test_partial_week_does_not_affect_official_signal(cfg):
    data = synthetic_data(days=2000)
    last = data["coinmetrics"]["date"].max()
    # katkaistaan viimeiseen sunnuntaihin → kaikki viikot suljettuja
    sunday = last - pd.Timedelta(days=(last.weekday() + 1) % 7)
    closed = evaluate(cfg, data, as_of=sunday)
    assert closed["preview"] is None
    # lisätään keskeneräinen viikko, jossa hinta romahtaa 90 %
    wild = {k: (v.copy() if v is not None else None) for k, v in data.items()}
    cm = wild["coinmetrics"]
    extra = cm[cm["date"] > sunday].head(3).copy()
    extra["PriceUSD"] *= 0.1
    extra["CapMrktCurUSD"] *= 0.1
    wild["coinmetrics"] = pd.concat([cm[cm["date"] <= sunday], extra])
    partial = evaluate(cfg, wild)
    assert partial["preview"] is not None
    assert not partial["preview"]["row"]["complete"]
    a, b = _official_frame(closed), _official_frame(partial)
    pd.testing.assert_frame_equal(a, b)


def test_no_lookahead_truncation(cfg):
    """Pisteet viikolle X ovat samat, laskettiinpa X:n jälkeistä dataa mukaan tai ei."""
    data = synthetic_data(days=2200, seed=3)
    full = _official_frame(evaluate(cfg, data))
    cut = pd.Timestamp("2019-06-02")  # sunnuntai
    part = _official_frame(evaluate(cfg, data, as_of=cut))
    pd.testing.assert_frame_equal(full.iloc[:len(part)].reset_index(drop=True), part)
