from metrics import compute_trade_stats, format_profit_factor


def test_no_trades_at_all():
    stats = compute_trade_stats([])
    assert stats.n_closed == 0
    assert stats.profit_factor is None
    assert format_profit_factor(stats.profit_factor) == "N/A - inga förlustaffärer"


def test_only_winning_trades():
    trades = [{"pnl": 10.0, "status": "closed"}, {"pnl": 5.0, "status": "closed"}]
    stats = compute_trade_stats(trades)
    assert stats.win_rate_pct == 100.0
    assert format_profit_factor(stats.profit_factor) == "∞"


def test_only_losing_trades():
    trades = [{"pnl": -10.0, "status": "closed"}, {"pnl": -5.0, "status": "closed"}]
    stats = compute_trade_stats(trades)
    assert stats.win_rate_pct == 0.0
    assert stats.profit_factor == 0.0
