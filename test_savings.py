"""Månadssparande: sparplan, insättningar i portföljmotorn, XIRR och tidsviktad avkastning."""
import numpy as np
import pandas as pd
import pytest

import portfolio
import savings


def test_contribution_schedule_monthly_growth_initial_and_extra():
    plan = savings.SavingsPlan(start=pd.Timestamp("2020-01-10"), end=pd.Timestamp("2021-03-31"),
                               initial_amount=5000, monthly_amount=1000, deposit_day=25, annual_increase_pct=10,
                               extra=[(pd.Timestamp("2020-06-01"), 20000), (pd.Timestamp("2019-01-01"), 999)])
    flows = savings.build_contributions(plan)
    assert flows[pd.Timestamp("2020-01-10")] == 5000          # startbelopp på startdagen
    assert flows[pd.Timestamp("2020-01-25")] == 1000          # första månadsinsättningen
    assert flows[pd.Timestamp("2020-12-25")] == 1000          # månad 12 (n = 11)
    assert flows[pd.Timestamp("2021-01-25")] == pytest.approx(1100)  # höjs efter tolv insättningar
    assert flows[pd.Timestamp("2020-06-01")] == 20000
    assert pd.Timestamp("2019-01-01") not in flows.index       # utanför perioden
    assert flows.sum() == pytest.approx(5000 + 12 * 1000 + 3 * 1100 + 20000)


def test_first_deposit_moves_to_next_month_when_day_passed():
    plan = savings.SavingsPlan(start=pd.Timestamp("2020-01-26"), end=pd.Timestamp("2020-03-31"), monthly_amount=100, deposit_day=25)
    assert list(savings.build_contributions(plan).index) == [pd.Timestamp("2020-02-25"), pd.Timestamp("2020-03-25")]


def test_map_to_trading_days_weekend_merge_and_end():
    cal = pd.bdate_range("2024-01-01", "2024-01-31")
    flows = pd.Series({pd.Timestamp("2024-01-06"): 100.0, pd.Timestamp("2024-01-08"): 50.0, pd.Timestamp("2024-02-10"): 7.0})
    out = savings.map_to_trading_days(flows, cal)
    assert out.to_dict() == {pd.Timestamp("2024-01-08"): 150.0}


def test_xirr_known_values():
    assert savings.xirr([pd.Timestamp("2023-01-01")], [100.0], pd.Timestamp("2024-01-01"), 110.0) == pytest.approx(0.10, abs=1e-6)
    # Två insättningar som båda växer 5 %/år.
    d0, d1, end = pd.Timestamp("2020-01-01"), pd.Timestamp("2021-01-01"), pd.Timestamp("2022-01-01")
    fv = 100 * 1.05 ** ((end - d0).days / 365) + 100 * 1.05 ** ((end - d1).days / 365)
    assert savings.xirr([d0, d1], [100.0, 100.0], end, fv) == pytest.approx(0.05, abs=1e-6)
    assert np.isnan(savings.xirr([], [], end, 0.0))


def _params(**kw):
    base = dict(base_weights={"a": 1.0}, scope_keys={"a"}, rebalance_freq="none", interest_mode="zero",
                derisk_pct=100.0, initial_capital=0.0)
    base.update(kw)
    return portfolio.PortfolioParams(**base)


def test_deposits_buy_at_that_days_price_and_go_to_cash_when_derisked():
    dates = pd.bdate_range("2024-01-01", periods=6)
    prices = pd.DataFrame({"a": [100, 100, 200, 200, 100, 100.0]}, index=dates)
    flows = pd.Series({dates[1]: 1000.0, dates[3]: 1000.0})
    bnh = portfolio.simulate_portfolio(prices, None, _params(apply_ki=False), cash_flows=flows)
    # 1000 kr köper 10 andelar à 100, värdet dubblas; 1000 kr köper 5 andelar à 200; sedan halveras priset.
    np.testing.assert_allclose(bnh["equity"].to_numpy(), [0, 1000, 2000, 3000, 1500, 1500])
    # KI säljer allt dag 2 => insättningen dag 3 hamnar på räntekontot och följer inte med i fallet.
    sell = pd.DataFrame({"Signal": [-1]}, index=[dates[2]])
    ki = portfolio.simulate_portfolio(prices, sell, _params(), cash_flows=flows)
    np.testing.assert_allclose(ki["equity"].to_numpy(), [0, 1000, 2000, 3000, 3000, 3000])
    assert ki["components"]["cash"].iloc[3] == pytest.approx(3000)


def test_deposit_cost_only_on_equity_part():
    dates = pd.bdate_range("2024-01-01", periods=2)
    prices = pd.DataFrame({"a": [100.0, 100.0]}, index=dates)
    flows = pd.Series({dates[1]: 1010.0})
    res = portfolio.simulate_portfolio(prices, None, _params(apply_ki=False, cost_bps=100), cash_flows=flows)
    assert res["equity"].iloc[-1] == pytest.approx(1000.0)
    assert res["transaction_costs"].iloc[-1] == pytest.approx(10.0)
    with pytest.raises(ValueError):
        portfolio.simulate_portfolio(prices, None, _params(), cash_flows=pd.Series({pd.Timestamp("2024-01-06"): 1.0}))


def test_without_flows_engine_is_unchanged():
    dates = pd.bdate_range("2024-01-01", periods=30)
    prices = pd.DataFrame({"a": np.linspace(100, 130, 30), "b": np.linspace(100, 90, 30)}, index=dates)
    sig = pd.DataFrame({"Signal": [-1, 1]}, index=[dates[5], dates[20]])
    p = portfolio.PortfolioParams({"a": .5, "b": .5}, rebalance_freq="monthly", derisk_pct=50, interest_mode="fixed",
                                  annual_interest_rate=.03, initial_capital=1000, cost_bps=5)
    a = portfolio.simulate_portfolio(prices, sig, p)
    b = portfolio.simulate_portfolio(prices, sig, p, cash_flows=pd.Series(dtype=float))
    pd.testing.assert_series_equal(a["equity"], b["equity"])


def test_twr_ignores_deposits_and_summary():
    dates = pd.bdate_range("2024-01-01", periods=5)
    prices = pd.DataFrame({"a": [100, 110, 110, 121, 121.0]}, index=dates)
    flows = pd.Series({dates[0]: 1000.0, dates[2]: 5000.0})
    res = portfolio.simulate_portfolio(prices, None, _params(apply_ki=False), cash_flows=flows)
    twr = savings.twr_series(res["equity"], flows)
    np.testing.assert_allclose(twr.to_numpy(), [1, 1.1, 1.1, 1.21, 1.21])
    summ = savings.summarize(res, flows)
    assert summ["invested"] == pytest.approx(6000)
    assert summ["final_value"] == pytest.approx(1000 * 1.21 + 5000 * 1.1)
    assert summ["max_dd_pct"] == pytest.approx(0.0)


def test_run_plan_constant_growth_gives_growth_rate():
    dates = pd.bdate_range("2015-01-01", "2020-12-31")
    years = (dates - dates[0]).days / 365.0
    prices = pd.DataFrame({"a": 100 * 1.07 ** years}, index=dates)
    plan = savings.SavingsPlan(start=dates[0], end=dates[-1], initial_amount=10000, monthly_amount=1000, annual_increase_pct=3)
    flows = savings.map_to_trading_days(savings.build_contributions(plan), dates)
    out = savings.run_plan(prices, None, _params(), flows)
    assert out["bnh_summary"]["xirr_pct"] == pytest.approx(7.0, abs=0.02)
    assert out["bnh_summary"]["twr_cagr_pct"] == pytest.approx(7.0, abs=0.05)
    # Utan signaler är KI och köp och behåll identiska.
    pd.testing.assert_series_equal(out["ki"]["equity"], out["bnh"]["equity"])


def test_parse_extra_deposits_any_number_of_rows():
    table = pd.DataFrame({
        "Datum": [pd.Timestamp("2021-06-01"), pd.Timestamp("2015-03-01"), None, pd.Timestamp("2018-01-01"), None,
                  pd.Timestamp("2019-01-01"), pd.Timestamp("2020-01-01"), pd.Timestamp("2022-01-01")],
        "Belopp (kr)": [30000, 50000, 1000, 0, None, 10000, 20000, 5000],
        "Beskrivning": ["Bonus", "Arv", "saknar datum", "noll", None, None, "Sålt bil", ""],
    })
    rows, incomplete = savings.parse_extra_deposits(table)
    assert [(n, d.year, a, lbl) for n, d, a, lbl in rows] == [
        (2, 2015, 50000.0, "Arv"), (6, 2019, 10000.0, ""), (7, 2020, 20000.0, "Sålt bil"),
        (1, 2021, 30000.0, "Bonus"), (8, 2022, 5000.0, "")]
    assert incomplete == 2  # rad 3 (saknar datum) och rad 4 (0 kr); helt tom rad 5 ignoreras
    assert savings.parse_extra_deposits(savings.empty_extra_table()) == ([], 0)
    assert savings.parse_extra_deposits(None) == ([], 0)
