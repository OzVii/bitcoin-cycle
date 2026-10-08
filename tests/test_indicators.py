import numpy as np
import pandas as pd
import pytest

import indicators as ind


def S(vals):
    return pd.Series(vals, dtype=float)


def test_sma():
    out = ind.sma(S([1, 2, 3, 4, 5]), 3)
    assert out.isna().sum() == 2
    assert out.tolist()[2:] == [2.0, 3.0, 4.0]


def test_ema_seeded_with_sma():
    s = S([1, 2, 3, 4, 5, 6])
    out = ind.ema(s, 3)
    a = 2 / 4
    exp = [np.nan, np.nan, 2.0]
    for v in [4, 5, 6]:
        exp.append(a * v + (1 - a) * exp[-1])
    np.testing.assert_allclose(out.to_numpy(), exp, equal_nan=True)


def test_ema_constant():
    np.testing.assert_allclose(ind.ema(S([7.0] * 50), 10).dropna().to_numpy(), 7.0)


def _rsi_reference(prices, n):
    """Wilderin RSI suoraan määritelmästä."""
    d = np.diff(prices)
    g, l = np.maximum(d, 0), np.maximum(-d, 0)
    ag, al = g[:n].mean(), l[:n].mean()
    out = [np.nan] * n + [100 - 100 / (1 + ag / al)]
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out.append(100 - 100 / (1 + ag / al))
    return np.array(out)


def test_rsi_matches_wilder_reference():
    rng = np.random.default_rng(0)
    p = 100 + np.cumsum(rng.normal(0, 1, 200))
    np.testing.assert_allclose(ind.rsi(S(p), 14).to_numpy(), _rsi_reference(p, 14), equal_nan=True, rtol=1e-10)


def test_rsi_extremes():
    assert ind.rsi(S(range(1, 40)), 14).dropna().eq(100).all()
    assert ind.rsi(S(range(40, 1, -1)), 14).dropna().eq(0).all()


def test_macd_linear_series():
    # Lineaarisessa sarjassa EMA(n) jää jälkeen (n−1)/2 askelta → MACD → (26−1)/2 − (12−1)/2 = 7
    m = ind.macd(S(np.arange(600.0)), 12, 26, 9)
    assert m["macd"].iloc[-1] == pytest.approx(7.0, abs=1e-6)
    assert m["signal"].iloc[-1] == pytest.approx(7.0, abs=1e-6)
    assert m["hist"].iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_mvrv_z():
    mcap = S([100, 110, 120, 130])
    mvrv = S([2, 2, 2, 2])
    z = ind.mvrv_z(mcap, mvrv, min_periods=2)
    assert np.isnan(z["z"].iloc[0])
    sd = np.std([100, 110, 120], ddof=1)
    assert z["z"].iloc[2] == pytest.approx((120 - 60) / sd)
    # myyntitaso: hinta, jolla z olisi annettu arvo
    supply = 10.0
    p = ind.mvrv_z_price(z["realized_cap"].iloc[2], z["sigma"].iloc[2], supply, z["z"].iloc[2])
    assert p == pytest.approx(120 / supply)


def test_mvrv_z_no_lookahead():
    rng = np.random.default_rng(1)
    mcap = S(rng.uniform(50, 150, 300))
    mvrv = S(rng.uniform(1, 3, 300))
    for window in (None, 60):
        full = ind.mvrv_z(mcap, mvrv, 30, window)["z"]
        part = ind.mvrv_z(mcap[:200], mvrv[:200], 30, window)["z"]
        np.testing.assert_allclose(full[:200].to_numpy(), part.to_numpy(), equal_nan=True)


def test_mvrv_z_rolling_window():
    mcap = S([100, 200, 110, 120, 130])
    z = ind.mvrv_z(mcap, S([2.0] * 5), min_periods=2, window=3)
    assert z["sigma"].iloc[4] == pytest.approx(np.std([110, 120, 130], ddof=1))


def test_puell():
    iss = S([10.0] * 400)
    assert ind.puell(iss, 365).dropna().eq(1.0).all()
    iss2 = S([10.0] * 365 + [20.0])
    assert ind.puell(iss2, 365).iloc[-1] == pytest.approx(20 / ((364 * 10 + 20) / 365))


def test_pi_cycle_cross_and_distance():
    price = S(np.r_[np.full(400, 100.0), np.linspace(100, 2000, 200)])
    pi = ind.pi_cycle(price, 111, 350, 2)
    i = pi.index[pi["pi_cross"]]
    assert len(i) == 1
    c = i[0]
    assert pi["pi_sma111"].iloc[c] >= pi["pi_upper"].iloc[c]
    assert pi["pi_sma111"].iloc[c - 1] < pi["pi_upper"].iloc[c - 1]
    # tasaisella hinnalla 111 DMA:n pitää kaksinkertaistua → etäisyys 100 %
    assert pi["pi_dist_pct"].iloc[399] == pytest.approx(100.0)


def test_days_since_halving():
    d = pd.Series(pd.to_datetime(["2012-01-01", "2012-11-28", "2016-07-10"]))
    out = ind.days_since_halving(d, ["2012-11-28", "2016-07-09"])
    assert np.isnan(out.iloc[0]) and out.iloc[1] == 0 and out.iloc[2] == 1


def test_support_band_confirmation():
    close = S([10, 12, 13, 9, 13, 8, 7])
    top = S([11] * 7)
    bot = S([10] * 7)
    st = ind.support_band_state(close, top, bot, confirm=2)
    assert st["band_state"].tolist() == ["inside", "above", "above", "below", "above", "below", "below"]
    assert st["trend"].tolist() == [None, None, "up", "up", "up", "up", "down"]
    assert st["band_streak"].tolist() == [1, 1, 2, 1, 1, 1, 2]


def _div_series():
    # kaksi huippua: toinen hinnaltaan korkeampi, RSI matalampi → karhumainen divergenssi
    price = [10, 11, 12, 15, 12, 11, 10, 11, 12, 13, 16, 13, 12, 11, 10]
    rsi = [50, 60, 70, 80, 70, 60, 50, 55, 60, 65, 70, 60, 55, 50, 45]
    return S(price), S(rsi)


def test_bearish_divergence_detected_causally():
    p, r = _div_series()
    df, ev = ind.find_divergences(p, r, left=2, right=2, min_gap=3, max_gap=20, active=3, bear_min=60)
    assert len(ev) == 1 and ev[0]["type"] == "bear"
    assert ev[0]["pivot_idx"] == 10 and ev[0]["prev_idx"] == 3
    assert ev[0]["confirmed_idx"] == 12  # vasta right-palkin jälkeen
    assert not df["div_bear"].iloc[:12].any()
    assert df["div_bear"].iloc[12:15].all()
    # sama tulos katkaistulla sarjalla → ei tulevaisuuden dataa
    df2, _ = ind.find_divergences(p[:12], r[:12], left=2, right=2, min_gap=3, max_gap=20, active=3, bear_min=60)
    assert not df2["div_bear"].any()


def test_bullish_divergence():
    p, r = _div_series()
    df, ev = ind.find_divergences(-p + 30, 100 - r, left=2, right=2, min_gap=3, max_gap=20, active=3,
                                  bull_max=45)
    assert [e["type"] for e in ev] == ["bull"]
    assert df["div_bull"].iloc[12]


def test_weekly_aggregation_monday_weeks():
    dates = pd.date_range("2024-01-01", "2024-01-17", freq="D")  # ma 1.1. – ke 17.1.
    daily = pd.DataFrame({"date": dates, "price": np.arange(len(dates), dtype=float)})
    w = ind.to_weekly_last(daily)
    assert w["week_start"].dt.weekday.eq(0).all()
    assert w["date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-07", "2024-01-14", "2024-01-17"]
    assert w["complete"].tolist() == [True, True, False]


def test_prev_cycle_peak_is_causal():
    dates = pd.Series(pd.date_range("2019-01-06", "2026-01-04", freq="W-SUN"))
    vals = pd.Series(np.where(dates < pd.Timestamp("2021-06-01"), 1.0, 2.0))
    vals[dates == pd.Timestamp("2021-04-11")] = 9.0
    out = ind.prev_cycle_peak(dates, vals, ["2016-07-09", "2020-05-11", "2024-04-20"], min_valid=10)
    assert out[dates < pd.Timestamp("2020-05-11")].isna().all()  # ei edellistä jaksoa
    assert (out[(dates >= pd.Timestamp("2020-05-11")) & (dates < pd.Timestamp("2024-04-20"))] == 1.0).all()
    assert (out[dates >= pd.Timestamp("2024-04-20")] == 9.0).all()
    # vuoden 2021 huippu ei näy ennen vuoden 2024 halvingia
    assert not (out[dates < pd.Timestamp("2024-04-20")] == 9.0).any()


def test_fib_levels():
    f = ind.fib_levels(100, 200, [0.5], [1.618])
    assert f["retracements"][0]["price"] == pytest.approx(150)
    assert f["extensions"][0]["price"] == pytest.approx(261.8)
