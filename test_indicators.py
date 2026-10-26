import numpy as np
import pandas as pd

from indicators import compute_rsi, compute_sma, compute_trend_streak


def _dates(n):
    return pd.date_range("2020-01-01", periods=n, freq="B")


def test_rsi_warmup_is_nan():
    """RSI ska vara NaN tills tillräckligt många observationer finns - aldrig artificiellt 100."""
    prices = pd.Series(np.linspace(100, 120, 30), index=_dates(30))
    rsi = compute_rsi(prices, period=14)
    assert rsi.iloc[:14].isna().all()
    assert rsi.iloc[14:].notna().all()


def test_rsi_all_gains_is_100():
    prices = pd.Series(np.linspace(100, 200, 30), index=_dates(30))
    rsi = compute_rsi(prices, period=14)
    assert rsi.iloc[-1] == 100.0


def test_rsi_all_losses_is_0():
    prices = pd.Series(np.linspace(200, 100, 30), index=_dates(30))
    rsi = compute_rsi(prices, period=14)
    assert rsi.iloc[-1] == 0.0


def test_sma_period_respected():
    prices = pd.Series(np.arange(1, 21, dtype=float), index=_dates(20))
    sma = compute_sma(prices, period=5)
    assert sma.iloc[:4].isna().all()
    assert sma.iloc[4] == prices.iloc[0:5].mean()


def test_trend_streak_sign_and_growth():
    close = pd.Series([10, 11, 12, 9, 8, 13], index=_dates(6), dtype=float)
    sma = pd.Series([10, 10, 10, 10, 10, 10], index=_dates(6), dtype=float)
    streak = compute_trend_streak(close, sma)
    # dag0: 10>10 False -> negativ (t=-1) streak=-1 ; dag1:11>10 True streak=1; dag2:12>10 True streak=2
    # dag3: 9>10 False streak=-1; dag4: 8>10 False streak=-2; dag5: 13>10 True streak=1
    assert list(streak) == [-1, 1, 2, -1, -2, 1]
