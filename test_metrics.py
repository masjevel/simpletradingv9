import numpy as np
import pandas as pd

from metrics import cagr, max_drawdown, total_return


def _dates(n):
    return pd.date_range("2020-01-01", periods=n, freq="D")


def test_cagr_known_value():
    # Startar på 100, dubblas över exakt 1 år (365 dagar) -> CAGR ~ 100 %
    idx = pd.DatetimeIndex(["2020-01-01", "2021-01-01"])  # 366 dagar (skottår) men nära nog
    equity = pd.Series([100.0, 200.0], index=idx)
    result = cagr(equity)
    assert 90.0 < result < 110.0


def test_total_return_simple():
    equity = pd.Series([100.0, 150.0], index=_dates(2))
    assert total_return(equity) == 50.0


def test_max_drawdown_simple():
    equity = pd.Series([100.0, 120.0, 60.0, 90.0], index=_dates(4))
    mdd = max_drawdown(equity)
    assert round(mdd, 2) == -50.0
