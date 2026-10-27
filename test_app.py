"""Full UI smoke tests with synthetic replacements for all market-data fetchers."""
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize('fx_case', ['normal', 'future_only'])
def test_ui_history_and_reports_offline(monkeypatch, fx_case):
    dates = pd.bdate_range('2020-01-01', periods=300)
    close = 100 + np.arange(300)*.05 + 5*np.sin(np.arange(300)/7)
    prices = pd.DataFrame({'Close':close,'Open':close},index=dates)
    fake = types.ModuleType('data')
    fake.fetch_price_series = lambda *a, **k: prices.copy()
    fake.fetch_vix = lambda: pd.Series(25.,index=dates,name='VIX')
    fake.fetch_ki_barometer = lambda: pd.DataFrame({'Barometer':[115.,115.,115.,80.,80.,80.,95.,98.,100.,105.,110.,115.]},index=pd.date_range('2020-01-31',periods=12,freq='ME'))
    fx_dates=dates[3:] if fx_case=='normal' else pd.to_datetime(['2030-01-01'])
    fake.fetch_fx_rate=lambda:pd.Series(10.,index=fx_dates)
    fake.fetch_riksbank_rate = lambda *a, **k: pd.Series(0.01, index=pd.date_range('1995-01-02', '2030-12-31', freq='B'))
    fake.fetch_us_cli = lambda *a, **k: None
    monkeypatch.setitem(sys.modules,'data',fake)
    app=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=30).run()
    assert not app.exception
    if fx_case=='future_only':
        assert any('Otillräcklig gemensam historik' in e.value for e in app.error)
        return
    assert any('2020-01-06' in c.value and 'Faktisk backteststart' in c.value for c in app.caption)
    assert any('få konjunkturcykler' in w.value for w in app.warning)
    assert not app.sidebar.slider
    assert len(app.tabs[2].slider) == 3
    assert len(app.tabs)==5
    tech_before = {m.label:m.value for m in app.tabs[1].metric}
    before={m.label:m.value for m in app.metric}
    account=next(s for s in app.tabs[3].selectbox if s.label=='Räntekonto')
    account.set_value('zero').run()
    assert not app.exception
    assert any('Defensiv ränta: 0.0%' in c.value for c in app.markdown)
    assert tech_before == {m.label:m.value for m in app.tabs[1].metric}
    after={m.label:m.value for m in app.metric}
    assert before['Sharpe (KI) / (B&H)'] != after['Sharpe (KI) / (B&H)']

    value_before = next(m.value for m in app.tabs[3].metric if m.label=='Totalavkastning (Buy & Hold)')
    next(n for n in app.tabs[3].number_input if n.label=='Courtage/transaktionskostnad (bps)').set_value(100.)
    next(n for n in app.tabs[3].number_input if n.label=='Slippage (bps)').set_value(50.)
    app.run()
    assert not app.exception
    value_after = next(m.value for m in app.tabs[3].metric if m.label=='Totalavkastning (Buy & Hold)')
    assert value_after != value_before


    # Presentation-only and model-local controls must not leak into other reports.
    metrics_before = [m.value for m in app.metric]
    next(s for s in app.tabs[0].slider if s.label == 'Heatmap-intensitet').set_value(300).run()
    assert not app.exception
    assert metrics_before == [m.value for m in app.metric]
    ki_before = [m.value for m in app.tabs[3].metric]
    next(s for s in app.tabs[0].slider if s.label == 'SMA-period (huvudtrend)').set_value(50).run()
    assert not app.exception
    assert ki_before == [m.value for m in app.tabs[3].metric]
    assert any('SMA: 50 dagar' in m.value for m in app.tabs[1].markdown)
    # A failed technical symbol must not block independent KI calculations.
    fake.fetch_price_series = lambda symbol: None if symbol == 'INVALID' else prices.copy()
    app.text_input[0].set_value('INVALID').run()
    assert not app.exception
    assert app.tabs[3].metric

def test_signal_controls_reach_computation(monkeypatch):
    import signals
    import indicators
    import backtest
    import ki_model
    dates = pd.bdate_range('2019-01-01', periods=400)
    close = 100 + 12*np.sin(np.arange(400)/6)
    prices = pd.DataFrame({'Close':close,'Open':close*.99},index=dates)
    fake = types.ModuleType('data')
    fake.fetch_price_series = lambda *a, **k: prices.copy()
    fake.fetch_vix = lambda: pd.Series(35.,index=dates,name='VIX')
    fake.fetch_ki_barometer = lambda: pd.DataFrame({'Barometer':[115.,115.,115.,80.,80.,80.,95.,98.,100.,105.,110.,115.]},index=pd.date_range('2019-01-31',periods=12,freq='ME'))
    fake.fetch_fx_rate = lambda: pd.Series(10.,index=dates)
    fake.fetch_riksbank_rate = lambda *a, **k: pd.Series(0.01, index=pd.date_range('1995-01-02', '2030-12-31', freq='B'))
    fake.fetch_us_cli = lambda *a, **k: None
    monkeypatch.setitem(sys.modules,'data',fake)
    seen={}
    original=signals.generate_signals
    def capture(df,p):
        seen['signal_params']=p
        seen['signal_df']=original(df,p)
        return seen['signal_df']
    monkeypatch.setattr(signals,'generate_signals',capture)
    original_bt=backtest.run_technical_backtest
    def capture_bt(df,p):
        assert df is seen['signal_df']
        seen['execution']=p
        return original_bt(df,p)
    monkeypatch.setattr(backtest,'run_technical_backtest',capture_bt)
    app=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=30).run()
    assert not app.exception
    for label,value,attribute in [('RSI köpgräns',40,'buy_rsi_threshold'),('MACD/RSI säljfilter',75,'sell_rsi_filter'),('VIX paniktröskel',50.,'vix_panic_threshold'),('Signal-cooldown (handelsdagar)',5,'cooldown_bars')]:
        ki_before=[m.value for m in app.tabs[3].metric]
        next(w for w in app.tabs[0].slider if w.label == label).set_value(value).run()
        assert not app.exception
        assert getattr(seen['signal_params'],attribute)==value
        assert ki_before == [m.value for m in app.tabs[3].metric]
    before=seen['signal_df'].copy()
    next(w for w in app.tabs[0].slider if w.label=='Heatmap-intensitet').set_value(30).run()
    pd.testing.assert_frame_equal(before,seen['signal_df'])
    next(w for w in app.tabs[0].slider if w.label=='SMA-period (huvudtrend)').set_value(50).run()
    assert seen['signal_df']['SMA'].first_valid_index()==dates[49]
    next(w for w in app.tabs[1].selectbox if 'Execution' in w.label).set_value('Nästa dags öppning (Open)').run()
    assert seen['execution'].execution_method=='open'
    # KI analysis is separate from KI portfolio configuration.
    pf_before=[m.value for m in app.tabs[3].metric]
    next(w for w in app.tabs[2].slider if 'säljgräns' in w.label).set_value(140).run()
    assert not app.exception
    assert pf_before==[m.value for m in app.tabs[3].metric]
    next(w for w in app.tabs[3].slider if 'säljgräns' in w.label).set_value(140).run()
    assert not app.exception
    assert pf_before!=[m.value for m in app.tabs[3].metric]


def test_flat_or_up_available_and_independent_in_both_ki_tabs(monkeypatch):
    import ki_model
    dates = pd.bdate_range('2020-01-01', periods=300)
    prices = pd.DataFrame({'Close': 100 + np.arange(300) * .1}, index=dates)
    prices['Open'] = prices['Close']
    fake = types.ModuleType('data')
    fake.fetch_price_series = lambda *a, **k: prices.copy()
    fake.fetch_vix = lambda: pd.Series(25., index=dates, name='VIX')
    fake.fetch_ki_barometer = lambda: pd.DataFrame({'Barometer': [114., 114., 114., 89., 91., 95.]}, index=pd.date_range('2020-01-31', periods=6, freq='ME'))
    fake.fetch_fx_rate = lambda: pd.Series(10., index=dates)
    fake.fetch_riksbank_rate = lambda *a, **k: pd.Series(0.01, index=pd.date_range('1995-01-02', '2030-12-31', freq='B'))
    fake.fetch_us_cli = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, 'data', fake)
    calls = []
    original = ki_model.generate_ki_signals
    def capture(series, params):
        result = original(series, params)
        calls.append((params.buyback_rule, result['Signal'].tolist()))
        return result
    monkeypatch.setattr(ki_model, 'generate_ki_signals', capture)
    app = AppTest.from_file(str(Path(__file__).with_name('app.py')), default_timeout=30).run()
    assert not app.exception
    pf_before = [m.value for m in app.tabs[3].metric]
    calls.clear()
    app.selectbox(key='ki_buyback_rule').set_value('flat_or_up').run()
    assert not app.exception
    assert calls[0] == ('flat_or_up', [0, 0, -1, 0, 1, 0])
    assert calls[1][0] == 'classic'
    assert pf_before == [m.value for m in app.tabs[3].metric]
    app.slider(key='pf_pf_ki_floor_threshold').set_value(70).run()
    calls.clear()
    app.selectbox(key='pf_pf_ki_buyback_rule').set_value('flat_or_up').run()
    assert not app.exception
    assert calls[0] == calls[1] == ('flat_or_up', [0, 0, -1, 0, 1, 0])
    assert app.slider(key='pf_pf_ki_floor_threshold').disabled
    app.selectbox(key='pf_pf_ki_buyback_rule').set_value('classic').run()
    assert not app.exception
    assert not app.slider(key='pf_pf_ki_floor_threshold').disabled
