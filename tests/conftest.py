import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from common import load_config  # noqa: E402


@pytest.fixture
def cfg():
    return load_config()


def synthetic_data(days=2000, start="2015-01-05", seed=1):
    """Keinotekoinen CoinMetrics-tyylinen data (alkaa maanantaina)."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=days, freq="D")
    t = np.arange(days)
    price = 300 * np.exp(np.cumsum(rng.normal(0.001, 0.03, days)))
    supply = 1.4e7 + 1800 * t
    mvrv = 1.6 + 0.8 * np.sin(t / 220)
    cm = pd.DataFrame({
        "date": dates, "PriceUSD": price, "CapMVRVCur": mvrv, "CapMrktCurUSD": price * supply,
        "IssTotUSD": 1800 * price * (1 + rng.normal(0, 0.05, days)), "SplyCur": supply,
    })
    fng = pd.DataFrame({"date": dates, "fng": np.clip(50 + 30 * np.sin(t / 90), 0, 100)})
    m2_dates = pd.date_range("2013-01-01", dates[-1], freq="MS")
    m2 = pd.DataFrame({"date": m2_dates, "m2": 10000 * 1.005 ** np.arange(len(m2_dates))})
    dollar = pd.DataFrame({"date": dates, "dollar": 100 + 5 * np.sin(t / 60)})
    return {"coinmetrics": cm, "ohlc_daily": None, "fng": fng, "m2": m2, "dollar": dollar}
