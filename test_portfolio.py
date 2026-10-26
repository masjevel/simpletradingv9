import numpy as np
import pandas as pd
import pytest

from portfolio import (
    PortfolioParams,
    align_prices,
    simulate_portfolio,
    to_common_currency,
    validate_weights,
)


def test_weights_must_sum_to_100():
    assert validate_weights({"a": 0.5, "b": 0.5})
    assert not validate_weights({"a": 0.5, "b": 0.4})


def test_currency_conversion_multiplies_by_fx():
    idx = pd.date_range("2020-01-01", periods=3, freq="D")
    price_usd = pd.Series([10.0, 10.0, 10.0], index=idx)
    fx = pd.Series([10.0, 10.0, 10.0], index=idx)  # 1 USD = 10 SEK
    price_sek = to_common_currency(price_usd, fx)
    assert list(price_sek) == [100.0, 100.0, 100.0]


def test_invalid_weights_raises():
    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    prices = pd.DataFrame({"a": [100.0] * 5}, index=idx)
    params = PortfolioParams(base_weights={"a": 0.5}, rebalance_freq="none", initial_capital=1000.0)
    with pytest.raises(ValueError):
        simulate_portfolio(prices, None, params)


def test_partial_derisking_moves_correct_fraction_to_cash():
    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    prices = pd.DataFrame({"a": [100.0, 100.0, 100.0, 100.0, 100.0]}, index=idx)
    ki_signals = pd.DataFrame({"Signal": [-1]}, index=[idx[2]])
    params = PortfolioParams(
        base_weights={"a": 1.0}, rebalance_freq="none", scope_keys={"a"},
        derisk_pct=50.0, interest_mode="zero", initial_capital=1000.0, apply_ki=True,
    )
    result = simulate_portfolio(prices, ki_signals, params)
    # Efter avriskning (dag index 2) ska 50% ligga i "a" och 50% i cash (flat pris => inga värdeförändringar annars)
    row = result["components"].iloc[2]
    assert row["a"] == pytest.approx(500.0, rel=1e-6)
    assert row["cash"] == pytest.approx(500.0, rel=1e-6)


def test_full_derisking_moves_everything_to_cash():
    idx = pd.date_range("2020-01-01", periods=4, freq="B")
    prices = pd.DataFrame({"a": [100.0] * 4}, index=idx)
    ki_signals = pd.DataFrame({"Signal": [-1]}, index=[idx[1]])
    params = PortfolioParams(
        base_weights={"a": 1.0}, rebalance_freq="none", scope_keys={"a"},
        derisk_pct=100.0, interest_mode="zero", initial_capital=1000.0, apply_ki=True,
    )
    result = simulate_portfolio(prices, ki_signals, params)
    assert result["components"]["a"].iloc[1] == pytest.approx(0.0, abs=1e-6)
    assert result["components"]["cash"].iloc[1] == pytest.approx(1000.0, rel=1e-6)


def test_interest_account_grows_with_fixed_rate():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    idx = pd.DatetimeIndex([idx[0], idx[0] + pd.Timedelta(days=365)])  # exakt ett år mellan raderna
    prices = pd.DataFrame({"a": [100.0, 100.0]}, index=idx)
    ki_signals = pd.DataFrame({"Signal": [-1]}, index=[idx[0]])
    params = PortfolioParams(
        base_weights={"a": 1.0}, rebalance_freq="none", scope_keys={"a"},
        derisk_pct=100.0, interest_mode="fixed", annual_interest_rate=0.05,
        initial_capital=1000.0, apply_ki=True,
    )
    # OBS: signalen på idx[0] triggar bara ombalansering FÖRE ränteberäkningen på nästa rad, så cash blir
    # 1000 kr från och med rad 0. Ett år senare (rad 1) ska den ha förräntats med 5%.
    result = simulate_portfolio(prices, ki_signals, params)
    assert result["components"]["cash"].iloc[1] == pytest.approx(1050.0, rel=1e-3)


def test_zero_interest_mode_no_growth():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    idx = pd.DatetimeIndex([idx[0], idx[0] + pd.Timedelta(days=365)])
    prices = pd.DataFrame({"a": [100.0, 100.0]}, index=idx)
    ki_signals = pd.DataFrame({"Signal": [-1]}, index=[idx[0]])
    params = PortfolioParams(
        base_weights={"a": 1.0}, rebalance_freq="none", scope_keys={"a"},
        derisk_pct=100.0, interest_mode="zero", initial_capital=1000.0, apply_ki=True,
    )
    result = simulate_portfolio(prices, ki_signals, params)
    assert result["components"]["cash"].iloc[1] == pytest.approx(1000.0, rel=1e-6)


def test_rebalancing_restores_target_weights():
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    # "a" dubblas i värde, "b" står still -> utan rebalansering skulle vikterna glida isär
    a_prices = np.linspace(100, 200, 400)
    b_prices = np.full(400, 100.0)
    prices = pd.DataFrame({"a": a_prices, "b": b_prices}, index=idx)
    params = PortfolioParams(
        base_weights={"a": 0.5, "b": 0.5}, rebalance_freq="quarterly", scope_keys=set(),
        derisk_pct=0.0, interest_mode="zero", initial_capital=1000.0, apply_ki=False,
    )
    result = simulate_portfolio(prices, None, params)
    # Direkt efter en rebalanseringsdag ska vikterna vara nära 50/50 igen.
    weights = result["weights"]
    later_weights = weights.iloc[200]
    assert later_weights["a"] == pytest.approx(0.5, abs=0.05)


def test_buy_and_hold_benchmark_uses_same_rebalance_schedule():
    from portfolio import run_ki_vs_bnh

    idx = pd.date_range("2020-01-01", periods=100, freq="B")
    prices = pd.DataFrame({"a": np.linspace(100, 120, 100), "b": np.linspace(100, 90, 100)}, index=idx)
    params = PortfolioParams(
        base_weights={"a": 0.5, "b": 0.5}, rebalance_freq="monthly", scope_keys={"a", "b"},
        derisk_pct=50.0, interest_mode="zero", initial_capital=1000.0, apply_ki=True,
    )
    out = run_ki_vs_bnh(prices, None, params)
    assert out["bnh"]["equity"].iloc[0] == pytest.approx(1000.0)
    assert out["ki"]["equity"].iloc[0] == pytest.approx(1000.0)
