"""Indikaattorit. Kaikki funktiot ovat kausaalisia: arvo hetkellä t riippuu vain datasta ≤ t."""
import numpy as np
import pandas as pd


# ---------------------------------------------------------------- perusfunktiot

def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def _seeded_ewm(s: pd.Series, n: int, alpha: float) -> pd.Series:
    """Eksponentiaalinen keskiarvo, jonka alkuarvo on ensimmäisten n arvon SMA (TradingView-tyyli)."""
    vals = s.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    valid = np.flatnonzero(~np.isnan(vals))
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    f = valid[0]
    if np.isnan(vals[f:f + n]).any():
        raise ValueError("EMA: sarjassa aukkoja alkujakson jälkeen")
    prev = vals[f:f + n].mean()
    out[f + n - 1] = prev
    for i in range(f + n, len(vals)):
        v = vals[i]
        if not np.isnan(v):
            prev = alpha * v + (1 - alpha) * prev
        out[i] = prev
    return pd.Series(out, index=s.index)


def ema(s: pd.Series, n: int) -> pd.Series:
    return _seeded_ewm(s, n, 2.0 / (n + 1))


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilderin liukuva keskiarvo (RSI:n tasoitus)."""
    return _seeded_ewm(s, n, 1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = rma(d.clip(lower=0), n)
    loss = rma((-d).clip(lower=0), n)
    rs = gain / loss
    out = 100 - 100 / (1 + rs)
    out[(loss == 0) & gain.notna()] = 100.0
    return out


def macd(close: pd.Series, fast=12, slow=26, signal=9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


# ---------------------------------------------------------------- arvostus

def realized_price(price: pd.Series, mvrv: pd.Series) -> pd.Series:
    return price / mvrv


def mvrv_z(mcap: pd.Series, mvrv: pd.Series, min_periods: int = 365, window: int | None = None) -> pd.DataFrame:
    """MVRV Z = (markkina-arvo − realisoitu arvo) / σ(markkina-arvo).
    σ lasketaan taaksepäin katsovalla ikkunalla, jotta tulevaisuuden data ei vuoda:
    window=None → kasvava ikkuna (koko historia), muuten liukuva ikkuna (päivää)."""
    realized = mcap / mvrv
    if window:
        sigma = mcap.rolling(window, min_periods=min(min_periods, window)).std()
    else:
        sigma = mcap.expanding(min_periods=min_periods).std()
    return pd.DataFrame({"realized_cap": realized, "sigma": sigma, "z": (mcap - realized) / sigma})


def mvrv_z_price(realized_cap, sigma, supply, z):
    """Hinta, jolla MVRV Z olisi z: (realisoitu arvo + z·σ) / tarjonta."""
    return (realized_cap + z * sigma) / supply


def puell(issuance_usd: pd.Series, window: int = 365) -> pd.Series:
    return issuance_usd / issuance_usd.rolling(window, min_periods=window).mean()


def pi_cycle(price: pd.Series, short=111, long=350, mult=2.0) -> pd.DataFrame:
    s = sma(price, short)
    upper = mult * sma(price, long)
    dist = (upper / s - 1) * 100  # kuinka paljon 111 DMA:n pitää nousta risteämään
    cross = (s >= upper) & (s.shift(1) < upper.shift(1))
    return pd.DataFrame({"pi_sma111": s, "pi_upper": upper, "pi_dist_pct": dist, "pi_cross": cross})


def days_since_halving(dates: pd.Series, halvings) -> pd.Series:
    hv = pd.to_datetime(pd.Series(halvings)).sort_values().to_numpy()
    d = pd.to_datetime(dates).to_numpy()
    idx = np.searchsorted(hv, d, side="right") - 1
    out = np.where(idx >= 0, (d - hv[np.clip(idx, 0, None)]).astype("timedelta64[D]").astype(float), np.nan)
    return pd.Series(out, index=dates.index)


def prev_cycle_peak(dates: pd.Series, values: pd.Series, halvings, min_valid: int = 52) -> pd.Series:
    """Edellisen halving-jakson huippuarvo: hetkellä t ∈ [H_k, H_k+1) palautetaan max(values)
    jaksolta [H_k−1, H_k). Jakso on kokonaan menneisyydessä, joten tulevaa dataa ei käytetä.
    NaN, jos edellistä jaksoa ei ole tai siinä on alle min_valid havaintoa."""
    d = pd.to_datetime(dates).reset_index(drop=True)
    v = pd.Series(values).reset_index(drop=True)
    hv = sorted(pd.to_datetime(halvings))
    peaks = {}
    for k in range(1, len(hv)):
        m = (d >= hv[k - 1]) & (d < hv[k]) & v.notna()
        peaks[k] = float(v[m].max()) if m.sum() >= min_valid else float("nan")
    idx = np.searchsorted(np.array(hv, dtype="datetime64[ns]"), d.to_numpy(), side="right") - 1
    out = [peaks.get(int(k), float("nan")) for k in idx]
    return pd.Series(out, index=dates.index, dtype=float)


# ---------------------------------------------------------------- trendi

def support_band_state(close: pd.Series, band_top: pd.Series, band_bottom: pd.Series, confirm: int = 2) -> pd.DataFrame:
    """Viikkosulun sijainti bull market support bandiin nähden.
    state: above / below / inside, streak: peräkkäiset viikot samassa tilassa,
    trend: viimeisin vahvistettu suunta (up/down), vaatii `confirm` peräkkäistä sulkua."""
    state, streak, trend = [], [], []
    cur_trend, prev_state, n = None, None, 0
    for c, top, bot in zip(close, band_top, band_bottom):
        if np.isnan(top) or np.isnan(bot) or np.isnan(c):
            st = None
        elif c > top:
            st = "above"
        elif c < bot:
            st = "below"
        else:
            st = "inside"
        n = n + 1 if (st == prev_state and st is not None) else (1 if st is not None else 0)
        if st == "above" and n >= confirm:
            cur_trend = "up"
        elif st == "below" and n >= confirm:
            cur_trend = "down"
        state.append(st)
        streak.append(n)
        trend.append(cur_trend)
        prev_state = st
    return pd.DataFrame({"band_state": pd.Series(state, index=close.index, dtype=object),
                         "band_streak": pd.Series(streak, index=close.index),
                         "trend": pd.Series(trend, index=close.index, dtype=object)})


def slope_pct(s: pd.Series, periods: int) -> pd.Series:
    return (s / s.shift(periods) - 1) * 100


# ---------------------------------------------------------------- divergenssit

def find_divergences(price: pd.Series, osc: pd.Series, left=3, right=2, min_gap=4, max_gap=40,
                     active=6, bear_min=60, bull_max=45):
    """Tunnistaa RSI-divergenssit pivot-pisteistä kausaalisesti.

    Pivot-huippu kohdassa p vahvistuu vasta kohdassa p + right, joten tapahtuma kirjataan
    vahvistushetkelle. Karhumainen: hinnan huippu korkeampi kuin edellinen, RSI matalampi
    (ja edellinen RSI-huippu ≥ bear_min). Härkämäinen päinvastoin pohjille.

    Palauttaa (DataFrame[bear_active, bull_active], tapahtumalista)."""
    p = price.to_numpy(dtype=float)
    o = osc.to_numpy(dtype=float)
    n = len(p)
    bear_active = np.zeros(n, dtype=bool)
    bull_active = np.zeros(n, dtype=bool)
    events = []
    highs, lows = [], []
    last_bear = last_bull = -10**9
    for t in range(n):
        piv = t - right
        if piv - left >= 0 and not np.isnan(o[piv - left:t + 1]).any():
            window_l = slice(piv - left, piv)
            window_r = slice(piv + 1, t + 1)
            if p[piv] > p[window_l].max() and p[piv] >= p[window_r].max():
                for q in reversed(highs):
                    gap = piv - q
                    if gap < min_gap:
                        continue
                    if gap > max_gap:
                        break
                    if p[piv] > p[q] and o[piv] < o[q] and o[q] >= bear_min:
                        last_bear = t
                        events.append({"type": "bear", "confirmed_idx": t, "pivot_idx": piv, "prev_idx": q})
                    break
                highs.append(piv)
            if p[piv] < p[window_l].min() and p[piv] <= p[window_r].min():
                for q in reversed(lows):
                    gap = piv - q
                    if gap < min_gap:
                        continue
                    if gap > max_gap:
                        break
                    if p[piv] < p[q] and o[piv] > o[q] and o[q] <= bull_max:
                        last_bull = t
                        events.append({"type": "bull", "confirmed_idx": t, "pivot_idx": piv, "prev_idx": q})
                    break
                lows.append(piv)
        bear_active[t] = t - last_bear < active
        bull_active[t] = t - last_bull < active
    df = pd.DataFrame({"div_bear": bear_active, "div_bull": bull_active}, index=price.index)
    return df, events


# ---------------------------------------------------------------- aikasarjojen koostaminen

def week_start(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    return (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.normalize()


def to_weekly_last(daily: pd.DataFrame) -> pd.DataFrame:
    """Viikon viimeinen päivärivi (viikko ma–su). Lisää sarakkeet week_start, week_end, complete."""
    df = daily.copy()
    df["week_start"] = week_start(df["date"])
    w = df.groupby("week_start", sort=True).tail(1).copy()
    w["week_end"] = w["week_start"] + pd.Timedelta(days=6)
    w["complete"] = w["date"] >= w["week_end"]
    return w.reset_index(drop=True)


def to_weekly_ohlc(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    df["week_start"] = week_start(df["date"])
    g = df.groupby("week_start", sort=True)
    w = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "last_date": g["date"].max(),
    }).reset_index()
    w["complete"] = w["last_date"] >= w["week_start"] + pd.Timedelta(days=6)
    return w


def to_monthly_last(daily: pd.DataFrame) -> pd.DataFrame:
    df = daily.copy()
    df["month"] = df["date"].dt.to_period("M")
    m = df.groupby("month", sort=True).tail(1).copy()
    m["month_end"] = m["month"].dt.end_time.dt.normalize()
    m["complete"] = m["date"] >= m["month_end"]
    return m.reset_index(drop=True)


# ---------------------------------------------------------------- syklit ja Fibonacci

def find_cycles(daily: pd.DataFrame, halvings, top_window=900, bottom_window=600, confirm_drawdown=0.5):
    """Syklien huiput ja pohjat halvingeista johdettuna.
    pohja ennen halvingia = min sulku edellisen syklin huipun ja halvingin välillä
      (ensimmäiselle syklille: korkeimman hinnan jälkeen jaksolla [H − bottom_window, H])
    huippu = max sulku jaksolla [pohja, H + top_window]
    huippu vahvistettu, jos hinta on sen jälkeen pudonnut ≥ confirm_drawdown."""
    s = daily.set_index("date")["price"].dropna()
    cycles = []
    prev_top = None
    for h in pd.to_datetime(halvings):
        if h > s.index[-1]:
            continue
        if prev_top is None:
            win = s[(s.index >= h - pd.Timedelta(days=bottom_window)) & (s.index <= h)]
            if win.empty:
                continue
            prev_top = win.idxmax()
        pre = s[(s.index >= prev_top) & (s.index <= h)]
        if pre.empty:
            continue
        b_date = pre.idxmin()
        post = s[(s.index >= b_date) & (s.index <= h + pd.Timedelta(days=top_window))]
        t_date = post.idxmax()
        prev_top = t_date
        after = s[s.index > t_date]
        confirmed = bool(len(after)) and after.min() <= s[t_date] * (1 - confirm_drawdown)
        cycles.append({
            "halving": h.strftime("%Y-%m-%d"),
            "bottom_date": b_date.strftime("%Y-%m-%d"), "bottom_price": float(s[b_date]),
            "top_date": t_date.strftime("%Y-%m-%d"), "top_price": float(s[t_date]),
            "top_confirmed": confirmed,
            "top_days_after_halving": int((t_date - h).days),
            "bottom_days_before_halving": int((h - b_date).days),
        })
    # bear-markkinan pohja huipun jälkeen (seuraavan syklin pohja)
    for i, c in enumerate(cycles):
        if i + 1 < len(cycles):
            c["next_bottom_date"] = cycles[i + 1]["bottom_date"]
            c["next_bottom_days_after_halving"] = int(
                (pd.Timestamp(cycles[i + 1]["bottom_date"]) - pd.Timestamp(c["halving"])).days)
    return cycles


def fib_levels(low, high, retracements, extensions, scale="linear"):
    def lerp(r):
        if scale == "log":
            return float(np.exp(np.log(low) + r * (np.log(high) - np.log(low))))
        return float(low + r * (high - low))
    return {
        "low": low, "high": high, "scale": scale,
        "retracements": [{"ratio": r, "price": lerp(1 - r)} for r in retracements],
        "extensions": [{"ratio": e, "price": lerp(e)} for e in extensions],
    }
