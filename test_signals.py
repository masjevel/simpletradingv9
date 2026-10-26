import numpy as np
import pandas as pd

from signals import SignalParams, generate_signals


def _base_df(n=60):
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    df = pd.DataFrame(index=dates)
    df["Close"] = 100.0
    df["SMA"] = 100.0
    df["RSI"] = 50.0
    df["MACD"] = 0.0
    df["MACD_Signal"] = 0.0
    df["VIX"] = 15.0
    return df


def test_no_signal_before_indicators_ready():
    df = _base_df()
    df.loc[df.index[:5], "RSI"] = np.nan
    params = SignalParams(buy_rsi_threshold=90, sell_rsi_filter=1, vix_panic_threshold=0.0, cooldown_bars=0)
    out = generate_signals(df, params)
    assert (out.iloc[:5]["Signal"] == 0).all()


def test_single_final_signal_per_day_on_conflict():
    """Om både köp- och säljvillkor är sanna samma dag ska ENDAST en entydig signal skrivas."""
    df = _base_df(5)
    df["RSI"] = 90.0  # skulle uppfylla sell_rsi_filter
    df["MACD"] = [1, 1, -1, -1, -1]
    df["MACD_Signal"] = [0, 0, 0, 0, 0]  # cross down sker på index 2
    df["VIX"] = 100.0  # vix panic buy candidate every day
    params = SignalParams(buy_rsi_threshold=95, sell_rsi_filter=50, vix_panic_threshold=10.0, cooldown_bars=0)
    out = generate_signals(df, params)
    # varje rad ska ha exakt en signaltyp, aldrig både köp och sälj samtidigt (per konstruktion finns bara en kolumn)
    assert set(out["Signal"].unique()).issubset({-1, 0, 1})
    # på index 2 båda villkoren sanna -> sälj vinner enligt prioriteringsregeln
    assert out["Signal"].iloc[2] == -1


def test_cooldown_prevents_repeat_signal():
    df = _base_df(10)
    df["RSI"] = 5.0  # alltid köpvärt
    params = SignalParams(buy_rsi_threshold=50, sell_rsi_filter=999, vix_panic_threshold=999, cooldown_bars=3)
    out = generate_signals(df, params)
    buy_idxs = np.where(out["Signal"].to_numpy() == 1)[0]
    assert len(buy_idxs) >= 2
    assert np.all(np.diff(buy_idxs) > 3)
