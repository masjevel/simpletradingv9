import numpy as np
import pandas as pd

from backtest import ExecutionParams, run_technical_backtest


def _make_df(closes, signal_idx_type):
    n = len(closes)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    df = pd.DataFrame(index=dates)
    df["Close"] = closes
    df["Open"] = closes
    df["SMA"] = closes[0]  # dummy, non-NaN so all rows are "valid"
    df["Signal"] = 0
    df["Signal_Type"] = None
    for i, (sig, typ) in signal_idx_type.items():
        df.iloc[i, df.columns.get_loc("Signal")] = sig
        df.iloc[i, df.columns.get_loc("Signal_Type")] = typ
    return df


def test_execution_happens_next_bar_not_same_day():
    closes = [100, 100, 200, 200, 200]  # jump happens at index 2
    df = _make_df(closes, {1: (1, "KÖP")})  # buy signal fires at index1 (close=100)
    params = ExecutionParams(initial_capital=1000.0, execution_method="close")
    result = run_technical_backtest(df, params)
    # Köp ska ske vid index 2 (t+1), dvs till pris 200 - INTE till priset 100 samma dag som signalen.
    trade = result["trades"][0]
    assert trade["entry_price"] == 200.0


def test_no_signal_no_trades():
    closes = [100, 101, 102, 103, 104]
    df = _make_df(closes, {})
    result = run_technical_backtest(df, ExecutionParams())
    assert result["trades"] == []


def test_open_position_marked_separately():
    closes = [100, 100, 110, 120, 130]
    df = _make_df(closes, {1: (1, "KÖP")})
    result = run_technical_backtest(df, ExecutionParams(initial_capital=1000.0))
    assert len(result["trades"]) == 1
    assert result["trades"][0]["status"] == "open"


def test_winning_trade_pnl_positive():
    closes = [100, 100, 100, 200, 200]
    df = _make_df(closes, {1: (1, "KÖP"), 3: (-1, "SÄLJ")})
    result = run_technical_backtest(df, ExecutionParams(initial_capital=1000.0))
    trade = result["trades"][0]
    assert trade["status"] == "closed"
    assert trade["pnl"] > 0


def test_losing_trade_pnl_negative():
    closes = [100, 100, 100, 50, 50]
    df = _make_df(closes, {1: (1, "KÖP"), 3: (-1, "SÄLJ")})
    result = run_technical_backtest(df, ExecutionParams(initial_capital=1000.0))
    trade = result["trades"][0]
    assert trade["pnl"] < 0


def test_costs_reduce_pnl():
    closes = [100, 100, 100, 200, 200]
    df = _make_df(closes, {1: (1, "KÖP"), 3: (-1, "SÄLJ")})
    cheap = run_technical_backtest(df, ExecutionParams(initial_capital=1000.0, cost_bps=0.0, slippage_bps=0.0))
    costly = run_technical_backtest(df, ExecutionParams(initial_capital=1000.0, cost_bps=50.0, slippage_bps=50.0))
    assert costly["trades"][0]["pnl"] < cheap["trades"][0]["pnl"]


def test_profit_factor_uses_dollar_pnl_not_percent():
    from metrics import compute_trade_stats

    trades = [
        {"pnl": 1000.0, "status": "closed"},
        {"pnl": -100.0, "status": "closed"},
    ]
    stats = compute_trade_stats(trades)
    assert stats.profit_factor == 10.0


def test_no_losing_trades_gives_infinite_pf():
    from metrics import compute_trade_stats
    import math

    trades = [{"pnl": 100.0, "status": "closed"}]
    stats = compute_trade_stats(trades)
    assert math.isinf(stats.profit_factor)


def test_open_trade_excluded_from_closed_stats():
    from metrics import compute_trade_stats

    trades = [
        {"pnl": 100.0, "status": "closed"},
        {"pnl": 9999.0, "status": "open"},
    ]
    stats = compute_trade_stats(trades)
    assert stats.n_closed == 1
    assert stats.n_open == 1
    assert stats.gross_profit == 100.0
