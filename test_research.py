from pathlib import Path
import ast
import sys
import types

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
import research
import portfolio
import ki_model
from signals import SignalParams, generate_signals
from test_signals import _base_df


def test_app_compiles():
    ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))


def test_disabled_sources_and_filters():
    df = _base_df(4)
    df['RSI'] = [20, 20, 20, 20]
    df['MACD'] = [1, -1, 1, -1]
    assert not generate_signals(df, SignalParams(use_rsi_buy=False, use_vix_buy=False, use_macd_sell=False))['Signal'].any()
    assert generate_signals(df, SignalParams(use_rsi_buy=False, use_vix_buy=False, use_rsi_sell_filter=False))['Signal'].tolist() == [0, -1, 0, 0]
    assert not generate_signals(df, SignalParams(use_trend_filter=True))['Signal'].any()
    df['Close'] = 101
    assert generate_signals(df, SignalParams(use_trend_filter=True))['Signal'].iloc[0] == 1


def test_disabled_indicators_do_not_block_warmup():
    df = _base_df(3)
    df[['RSI', 'MACD', 'MACD_Signal']] = np.nan
    df['VIX'] = 50
    out = generate_signals(df, SignalParams(use_rsi_buy=False, use_macd_sell=False))
    assert out['Signal'].iloc[0] == 1


def test_trend_waits_for_previous_close_and_cancels_on_sell():
    dates = pd.bdate_range('2020-01-01', periods=7)
    reference = pd.Series([10, 9, 8, 12, 13, 14, 15], index=dates)
    orders = pd.DataFrame({'Signal': [-1, 1], 'Reason': ['sell', 'buy']}, index=dates[[0, 2]])
    result = research.trend_orders(orders, reference, dates, window=3)
    assert result.index.tolist() == [dates[0], dates[4]]  # rises day 3, trade day 4
    changed = reference.copy()
    changed.iloc[4:] = [1, 1, 1]
    assert research.trend_orders(orders, changed, dates, window=3).index.tolist() == [dates[0], dates[4]]
    orders.loc[dates[3]] = [-1, 'cancel']
    result = research.trend_orders(orders, reference, dates, window=3)
    assert result['Signal'].tolist() == [-1, -1]


def test_period_keeps_last_known_state_and_actual_start_order_wins():
    dates = pd.bdate_range('2020-01-01', periods=7)
    orders = pd.DataFrame({'Signal': [-1, 1, -1]}, index=dates[[0, 2, 6]])
    result = research.orders_for_period(orders, dates[4:])
    assert result.index.tolist() == [dates[4], dates[6]]
    assert result['Signal'].tolist() == [1, -1]
    orders.loc[dates[4]] = [-1]
    assert research.orders_for_period(orders.sort_index(), dates[4:])['Signal'].tolist() == [-1, -1]


def test_mapping_preperiod_signals_is_unique():
    monthly = pd.Series([115, 89, 91], index=pd.date_range('2020-01-31', periods=3, freq='ME'))
    signals = ki_model.generate_ki_signals(monthly, ki_model.KiParams(110, 90, 1, 90, 'flat_or_up'))
    result = ki_model.map_signals_to_trading_days(signals, pd.bdate_range('2021-01-01', periods=4))
    assert len(result) == 1
    assert result['Signal'].iloc[0] == 1


def test_drawdown_duration_and_completed_cycles():
    dates = pd.date_range('2020-01-01', periods=6)
    assert research.longest_underwater_days(pd.Series([1, 2, 3, 4, 5, 6], index=dates)) == 0
    assert research.longest_underwater_days(pd.Series([10, 8, 9, 10, 9, 8], index=dates)) == 3
    assert research.completed_cycles([{'signal': s} for s in [1, -1, 1, -1]]) == 1


def test_invalid_period_and_empty_period():
    frame = pd.DataFrame({'Close': [1, 2]}, index=pd.to_datetime(['2020-01-01', '2020-01-02']))
    with pytest.raises(ValueError):
        research.select_period(frame, '2021-01-01', '2020-01-01')
    assert research.select_period(frame, '2021-01-01', '2021-01-02').empty


@pytest.fixture
def offline_app(monkeypatch):
    dates = pd.bdate_range('2018-01-01', periods=900)
    x = np.arange(len(dates))
    prices = pd.DataFrame({'Close': 100 + x*.05 + 10*np.sin(x/45)}, index=dates)
    prices['Open'] = prices['Close']
    fake = types.ModuleType('data')
    def fetch(symbol):
        if symbol == config.PORTFOLIO_PROXIES['global']['ticker']:
            return prices.iloc[300:].copy()
        if symbol == config.PORTFOLIO_PROXIES['em']['ticker']:
            return prices.iloc[100:].copy()
        return prices.copy()
    fake.fetch_price_series = fetch
    fake.fetch_vix = lambda: pd.Series(35., index=dates, name='VIX')
    fake.fetch_fx_rate = lambda: pd.Series(10., index=dates)
    fake.fetch_riksbank_rate = lambda *a, **k: pd.Series(0.01, index=pd.date_range('1995-01-02', '2030-12-31', freq='B'))
    fake.fetch_ki_barometer = lambda: pd.DataFrame({'Barometer': [115., 115., 115., 89., 91., 95., 100., 105., 110., 115., 89., 92.] * 3}, index=pd.date_range('2018-01-31', periods=36, freq='ME'))
    monkeypatch.setitem(sys.modules, 'data', fake)
    return fake, AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=60).run()


def test_zero_weights_same_period_and_resets(offline_app, monkeypatch):
    fake, app = offline_app
    assert not app.exception
    captured = []
    original = portfolio.run_ki_vs_bnh
    def capture(prices, orders, params):
        result = original(prices, orders, params)
        captured.append((prices.copy(), orders.copy(), params, result))
        return result
    monkeypatch.setattr(portfolio, 'run_ki_vs_bnh', capture)
    app.slider(key='pf_w_global').set_value(0)
    app.slider(key='pf_w_sweden').set_value(100)
    app.slider(key='pf_w_em').set_value(0).run()
    assert not app.exception
    assert captured[0][0].index[0] == pd.Timestamp('2018-01-01')
    assert list(captured[0][0].columns) == ['sweden']
    assert not any(m.label == 'CAGR KI-strategi Sverige' for m in app.metric)
    frame, orders, params, result = captured[0]
    expected = original(frame, orders, params)
    pd.testing.assert_series_equal(result['ki']['equity'], expected['ki']['equity'])
    # A missing zero-weight asset must not stop the test.
    old_fetch = fake.fetch_price_series
    fake.fetch_price_series = lambda symbol: None if symbol in ('URTH', 'EEM') else old_fetch(symbol)
    app.run()
    assert not app.exception
    assert any(m.label == 'CAGR (KI-strategi)' for m in app.metric)
    fake.fetch_price_series = old_fetch
    app.slider(key='tech_buy_rsi_threshold').set_value(40)
    app.slider(key='ki_ki_sell_threshold').set_value(120)
    app.checkbox(key='pf_trend').set_value(True).run()
    assert not app.exception
    app.button(key='reset_pf').click().run()
    assert not app.exception
    assert app.slider(key='pf_w_global').value == 75
    assert not app.checkbox(key='pf_trend').value
    assert app.slider(key='tech_buy_rsi_threshold').value == 40
    assert app.slider(key='ki_ki_sell_threshold').value == 120
    app.button(key='reset_technical').click().run()
    assert app.slider(key='tech_buy_rsi_threshold').value == config.DEFAULT_BUY_RSI_THRESHOLD
    assert app.slider(key='ki_ki_sell_threshold').value == 120
    app.button(key='reset_ki').click().run()
    assert app.slider(key='ki_ki_sell_threshold').value == config.DEFAULT_KI_SELL_THRESHOLD


def test_display_only_and_common_dates(offline_app, monkeypatch):
    _, app = offline_app
    before = [m.value for m in app.metric]
    app.checkbox(key='tech_show_sma').set_value(False)
    app.checkbox(key='tech_show_rsi').set_value(False)
    app.checkbox(key='tech_show_macd').set_value(False)
    app.checkbox(key='tech_show_vix').set_value(False).run()
    assert not app.exception
    assert before == [m.value for m in app.metric]
    frames = []
    original = portfolio.run_ki_vs_bnh
    def capture(prices, orders, params):
        frames.append(prices.copy())
        return original(prices, orders, params)
    monkeypatch.setattr(portfolio, 'run_ki_vs_bnh', capture)
    app.radio(key='period_mode').set_value('Välj datum').run()
    app.date_input(key='period_start').set_value(pd.Timestamp('2019-06-01').date())
    app.date_input(key='period_end').set_value(pd.Timestamp('2020-06-01').date())
    frames.clear()
    app.run()
    assert not app.exception
    assert len(frames) == 2
    pd.testing.assert_index_equal(frames[0].index, frames[1].index)
    assert frames[0].index[0] >= pd.Timestamp('2019-06-01')
    assert frames[0].index[-1] <= pd.Timestamp('2020-06-01')
    app.checkbox(key='tech_use_rsi').set_value(False)
    app.checkbox(key='tech_use_vix').set_value(False).run()
    assert any('Inga köpsignaler' in x.value for x in app.warning)
    assert not app.exception


def test_empty_custom_period_is_explained(offline_app):
    _, app = offline_app
    app.radio(key='period_mode').set_value('Välj datum').run()
    app.date_input(key='period_start').set_value(pd.Timestamp('2025-01-01').date())
    app.date_input(key='period_end').set_value(pd.Timestamp('2025-02-01').date()).run()
    assert not app.exception
    assert any('Otillräcklig' in x.value for x in app.error)
