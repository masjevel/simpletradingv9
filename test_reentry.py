"""Tester för kombinerat återköp (reentry.py). Endast syntetiska data."""
import numpy as np
import pandas as pd
import pytest

import ki_model
import portfolio
import reentry
from reentry import ReentryParams, prepare_conditions, run_reentry_engine

OFF = dict(use_ki=False, use_vix=False, use_credit=False, use_rsi=False, use_trend=False, time_stop_months=0)


def _ki(values, start="2015-01-31"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="ME"), dtype=float)


def _run(ki, rp, calendar=None, reference=None, vix=None, credit=None, kp=None):
    kp = kp or ki_model.KiParams(110, 90, 2, 90, "classic", publication_lag_days=0)
    calendar = calendar if calendar is not None else pd.bdate_range(ki.index[0], ki.index[-1] + pd.Timedelta(days=40))
    cond = prepare_conditions(calendar, rp, reference=reference, vix=vix, credit_ratio=credit)
    return run_reentry_engine(ki, kp, calendar, cond, rp)


@pytest.mark.parametrize("rule", ["classic", "turn_1m", "turn_2m", "flat_or_up"])
@pytest.mark.parametrize("lag", [0, 20])
def test_ki_only_matches_classic_model(rule, lag):
    vals = [100, 112, 113, 115, 104, 95, 88, 86, 87, 89, 92, 95, 100, 111, 114, 116, 108, 99, 89, 85, 88, 91, 96]
    ki = _ki(vals)
    kp = ki_model.KiParams(110, 90, 2, 90, rule, publication_lag_days=lag)
    calendar = pd.bdate_range("2014-12-01", "2017-03-31")
    rp = ReentryParams(**{**OFF, "use_ki": True})
    res = run_reentry_engine(ki, kp, calendar, prepare_conditions(calendar, rp), rp)
    classic = ki_model.map_signals_to_trading_days(ki_model.generate_ki_signals(ki, kp), calendar)
    assert list(res["orders"].index) == list(classic.index)
    assert res["orders"]["Signal"].tolist() == classic["Signal"].tolist()
    assert set(res["orders"].loc[res["orders"]["Signal"] == 1, "Exposure"]) <= {1.0}


def test_staged_steps_and_time_stop():
    ki = _ki([120, 120, 120] + [105] * 30)
    calendar = pd.bdate_range("2015-01-01", "2017-12-29")
    vix = pd.Series(15.0, index=calendar)
    vix.loc["2015-09-01":"2015-09-10"] = 45.0
    rp = ReentryParams(**{**OFF, "use_ki": True, "use_vix": True, "vix_calm_level": 0, "time_stop_months": 18})
    res = _run(ki, rp, calendar=calendar, vix=vix)
    o = res["orders"]
    assert o["Signal"].tolist() == [-1, 1, 1]
    assert o["Exposure"].tolist() == [0.0, 0.5, 1.0]
    assert o["Trigger"].tolist() == ["sell", "vix", "time"]
    # VIX vid stängning 1 sept används först nästa handelsdag.
    assert o.index[1] == pd.Timestamp("2015-09-02")
    cyc = res["cycles"][0]
    assert o.index[2] == calendar[calendar.searchsorted(cyc["time_stop_date"])]
    assert not res["state"]["out"]


def test_all_on_first_signal_when_not_staged():
    ki = _ki([120, 120, 120] + [105] * 12)
    calendar = pd.bdate_range("2015-01-01", "2016-06-30")
    vix = pd.Series(15.0, index=calendar)
    vix.loc["2015-09-01"] = 45.0
    rp = ReentryParams(**{**OFF, "use_ki": True, "use_vix": True, "vix_calm_level": 0, "staged": False})
    o = _run(ki, rp, calendar=calendar, vix=vix)["orders"]
    assert o["Exposure"].tolist() == [0.0, 1.0]


def test_vix_waits_for_calm_and_ignores_panic_before_sale():
    ki = _ki([120, 120, 120] + [105] * 12)
    calendar = pd.bdate_range("2015-01-01", "2016-06-30")
    vix = pd.Series(15.0, index=calendar)
    vix.loc["2015-02-02":"2015-02-20"] = 50.0  # före försäljningen
    rp = ReentryParams(**{**OFF, "use_vix": True, "vix_calm_level": 25})
    o = _run(ki, rp, calendar=calendar, vix=vix)["orders"]
    assert o["Signal"].tolist() == [-1]
    vix.loc["2015-08-03":"2015-08-14"] = 40.0
    vix.loc["2015-08-17":"2015-08-31"] = 30.0
    o = _run(ki, rp, calendar=calendar, vix=vix)["orders"]
    assert o.index[-1] == pd.Timestamp("2015-09-02")  # 1 sept är första dag under 25


def test_trend_requires_negative_period_after_sale():
    ki = _ki([120, 120, 120] + [105] * 20)
    calendar = pd.bdate_range("2014-01-01", "2016-12-30")
    x = np.arange(len(calendar), dtype=float)
    up = pd.Series(100 + x * 0.1, index=calendar)
    rp = ReentryParams(**{**OFF, "use_trend": True, "trend_mode": "daily_sma200"})
    o = _run(ki, rp, calendar=calendar, reference=up)["orders"]
    assert o["Signal"].tolist() == [-1]  # trenden var aldrig negativ: inget direkt återköp
    dip = up.copy()
    dip.loc["2015-06-01":"2015-09-30"] = 80.0
    o = _run(ki, rp, calendar=calendar, reference=dip)["orders"]
    assert o["Signal"].tolist() == [-1, 1]
    assert o.index[1] == pd.Timestamp("2015-10-02")  # 1 okt första stängning över, köp 2 okt


def test_no_lookahead_future_changes_do_not_alter_past_orders():
    ki = _ki([120, 120, 120] + [100] * 20)
    calendar = pd.bdate_range("2014-01-01", "2016-12-30")
    x = np.arange(len(calendar), dtype=float)
    ref = pd.Series(100 + 10 * np.sin(x / 30), index=calendar)
    vix = pd.Series(20 + 20 * np.sin(x / 17), index=calendar)
    credit = pd.Series(1 + 0.1 * np.sin(x / 40), index=calendar)
    rp = ReentryParams(use_ki=True, use_vix=True, use_credit=True, use_rsi=True, use_trend=True,
                       trend_mode="daily_sma200", time_stop_months=12)
    full = _run(ki, rp, calendar, ref, vix, credit)["orders"]
    cut = pd.Timestamp("2015-11-30")
    changed = [s.copy() for s in (ref, vix, credit)]
    for s in changed:
        s.loc[cut:] = s.loc[cut:] * 3
    alt = _run(ki, rp, calendar, *changed)["orders"]
    pd.testing.assert_frame_equal(full.loc[:cut], alt.loc[:cut])


def test_rearm_after_early_rebuy():
    # KI ligger kvar över säljgränsen efter VIX-återköp: ingen ny sälj förrän KI varit ≤ gränsen.
    ki = _ki([120, 120, 120, 120, 120, 120, 120, 105, 115, 116, 117])
    calendar = pd.bdate_range("2015-01-01", "2016-02-26")
    vix = pd.Series(15.0, index=calendar)
    vix.loc["2015-04-15"] = 45.0
    rp = ReentryParams(**{**OFF, "use_vix": True, "vix_calm_level": 0})
    o = _run(ki, rp, calendar=calendar, vix=vix)["orders"]
    assert o["Signal"].tolist() == [-1, 1, -1]
    assert o.index[2] > pd.Timestamp("2015-10-31")


def test_portfolio_partial_exposure():
    dates = pd.bdate_range("2020-01-01", periods=5)
    prices = pd.DataFrame({"a": 100.0}, index=dates)
    orders = pd.DataFrame({"Signal": [-1, 1, 1], "Exposure": [0.0, 0.5, 1.0]}, index=dates[[1, 2, 3]])
    p = portfolio.PortfolioParams({"a": 1.0}, scope_keys={"a"}, rebalance_freq="none", interest_mode="zero", derisk_pct=100)
    r = portfolio.simulate_portfolio(prices, orders, p)
    np.testing.assert_allclose(r["weights"]["cash"].to_numpy(), [0, 1, .5, 0, 0], atol=1e-12)
    assert [e["exposure"] for e in r["events"]] == [0.0, 0.5, 1.0]


def test_map_orders_to_calendar_keeps_last_state():
    orders = pd.DataFrame({"Signal": [-1, 1], "Exposure": [0.0, 0.5]},
                          index=pd.to_datetime(["2020-01-04", "2020-01-05"]))
    cal = pd.to_datetime(["2020-01-03", "2020-01-06", "2020-01-07"])
    out = reentry.map_orders_to_calendar(orders, cal)
    assert out.index.tolist() == [pd.Timestamp("2020-01-06")]
    assert out["Exposure"].iloc[0] == 0.5


def test_known_before_is_strict():
    cal = pd.bdate_range("2020-01-01", periods=3)
    s = pd.Series([1.0, 2.0, 3.0], index=cal)
    vals = reentry.known_before(s, cal)
    assert np.isnan(vals[0]) and vals[1] == 1.0 and vals[2] == 2.0


def test_expired_time_stop_before_calendar_resolves_on_first_day():
    ki = _ki([120, 120, 120] + [105] * 40, start="2010-01-31")
    calendar = pd.bdate_range("2013-01-01", "2013-06-28")
    rp = ReentryParams(**{**OFF, "use_vix": True, "time_stop_months": 12})
    o = _run(ki, rp, calendar=calendar)["orders"]
    assert len(o) == 1 and o.index[0] == calendar[0]
    assert o["Signal"].iloc[0] == 1 and o["Exposure"].iloc[0] == 1.0
