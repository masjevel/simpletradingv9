import numpy as np
import pandas as pd
import pytest

from ki_model import KiParams, generate_ki_signals, map_signals_to_trading_days


def _monthly(values):
    idx = pd.date_range("2020-01-31", periods=len(values), freq="ME")
    return pd.Series(values, index=idx)


@pytest.mark.parametrize("values,expected", [
    ([114, 89, 87], [-1, 0, 0]),
    ([114, 89, 89], [-1, 0, 1]),
    ([114, 89, 91], [-1, 0, 1]),
    ([114, 92, 94], [-1, 0, 0]),
    ([114, 90, 91], [-1, 0, 0]),
    ([89, 89, 91], [0, 0, 0]),
    ([114, 89, 87, 85, 86, 87], [-1, 0, 0, 0, 1, 0]),
    ([114, 89, 91, 114, 92, 94, 89, 89], [-1, 0, 1, -1, 0, 0, 0, 1]),
    ([114, 89, np.nan, 91, 91], [-1, 0, 0, 0, 1]),
])
@pytest.mark.parametrize("floor", [70, 100])
def test_flat_or_up_uses_buy_threshold_and_remembers_activation(values, expected, floor):
    params = KiParams(113, 90, 1, floor, "flat_or_up")
    out = generate_ki_signals(_monthly(values), params)
    assert out["Signal"].tolist() == expected


def test_flat_or_up_sell_duration_does_not_delay_buy():
    out = generate_ki_signals(_monthly([114, 114, 114, 89, 91]), KiParams(113, 90, 3, 70, "flat_or_up"))
    assert out["Signal"].tolist() == [0, 0, -1, 0, 1]
    assert out["State"].tolist() == ["NORMAL", "NORMAL", "DERISKED", "FLOOR_REACHED", "NORMAL"]
    trading_days = pd.bdate_range("2020-01-01", "2020-08-01")
    mapped = map_signals_to_trading_days(out, trading_days)
    assert mapped["Signal"].tolist() == [-1, 1]
    assert all(mapped.index > mapped["Available_Date"])


def test_flat_or_up_does_not_compare_across_missing_calendar_month():
    ki = pd.Series([114, 89, 91, 92], index=pd.to_datetime(["2020-01-31", "2020-02-29", "2020-04-30", "2020-05-31"]))
    out = generate_ki_signals(ki, KiParams(113, 90, 1, 90, "flat_or_up"))
    assert out["Signal"].tolist() == [-1, 0, 0, 1]


def test_sell_only_once_per_long_overheating_regime():
    """En lång överhettningsperiod (mycket längre än duration_months) ska bara ge EN säljsignal."""
    values = [105] + [115] * 20  # över säljgräns (110) i 20 månader i följd
    ki = _monthly(values)
    params = KiParams(sell_threshold=110, buy_threshold=90, duration_months=3, floor_threshold=90, buyback_rule="classic")
    out = generate_ki_signals(ki, params)
    assert (out["Signal"] == -1).sum() == 1


def test_classic_buyback_requires_duration_below_threshold():
    values = [115, 115, 115, 80, 80, 80, 80]
    ki = _monthly(values)
    params = KiParams(sell_threshold=110, buy_threshold=90, duration_months=3, floor_threshold=90, buyback_rule="classic")
    out = generate_ki_signals(ki, params)
    assert (out["Signal"] == -1).sum() == 1
    assert (out["Signal"] == 1).sum() == 1
    buy_idx = out.index[out["Signal"] == 1][0]
    assert values[list(ki.index).index(buy_idx)] == 80


def test_small_bounce_does_not_trigger_buyback_without_floor():
    """113 -> 115 -> 112 -> 113 ska INTE tolkas som botten (golv 90 aldrig passerat)."""
    values = [113, 113, 113, 115, 112, 113]  # sell after 3 months at 113 (index2), sen studs utan att nå golvet
    ki = _monthly(values)
    params = KiParams(sell_threshold=110, buy_threshold=90, duration_months=1, floor_threshold=90, buyback_rule="turn_1m")
    out = generate_ki_signals(ki, params)
    assert (out["Signal"] == 1).sum() == 0


def test_turn_up_1month_after_floor_reached():
    values = [115, 115, 115, 80, 79, 85]  # sälj vid 115x3, golv nås vid 80/79, vändning uppåt vid 85
    ki = _monthly(values)
    params = KiParams(sell_threshold=110, buy_threshold=90, duration_months=3, floor_threshold=90, buyback_rule="turn_1m")
    out = generate_ki_signals(ki, params)
    assert (out["Signal"] == 1).sum() == 1
    buy_idx = out.index[out["Signal"] == 1][0]
    assert values[list(ki.index).index(buy_idx)] == 85


def test_map_signals_to_trading_days_respects_lag_and_no_lookahead():
    values = [115, 115, 115]
    ki = _monthly(values)
    params = KiParams(sell_threshold=110, buy_threshold=90, duration_months=3, floor_threshold=90, buyback_rule="classic")
    signals = generate_ki_signals(ki, params)
    trading_days = pd.date_range("2020-01-01", "2020-06-01", freq="B")
    mapped = map_signals_to_trading_days(signals, trading_days)
    assert len(mapped) == 1
    exec_date = mapped.index[0]
    signal_month_end = signals.index[signals["Signal"] == -1][0]
    # exekveringsdatumet måste ligga EFTER själva signalmånadens slut (aldrig samma dag/tidigare)
    assert exec_date > signal_month_end
