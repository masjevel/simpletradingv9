import numpy as np
import pandas as pd
import pytest
import charts
from backtest import ExecutionParams, run_technical_backtest
from portfolio import PortfolioParams, simulate_portfolio
from test_backtest import _make_df


def test_actual_executions_and_open_trade_display():
    df = _make_df([100,110,120,130,140,150], {0:(1,'RSI KÖP'),2:(-1,'MACD SÄLJ'),4:(1,'VIX Panik KÖP'),5:(-1,'SÄLJ')})
    df['RSI'] = [20,30,70,60,40,50]
    result = run_technical_backtest(df, ExecutionParams(slippage_bps=10))
    events = charts.technical_events(result['trades'])
    assert len(events) == 3  # final sell signal cannot execute
    assert [e['date'] for e in events] == list(df.index[[1,3,5]])
    closed, opened = result['trades']
    assert closed['entry_signal_date'] == df.index[0]
    assert closed['exit_signal_date'] == df.index[2]
    assert closed['exit_indicators']['RSI'] == 70
    assert closed['entry_price'] == pytest.approx(110*1.001)
    log = charts.trade_log(result['trades'])
    assert pd.isna(log.iloc[1]['Säljdatum'])
    assert pd.isna(log.iloc[1]['Säljkurs'])
    fig = charts.build_equity_drawdown_chart(result['equity'], result['bnh_equity'], [0]*6, [0]*6)
    charts.add_transactions(fig,result['equity'],events,result['position'])
    assert sum(len(t.x) for t in fig.data if t.mode == 'markers+text') == 3
    assert sum(s.type == 'line' and s.x0 == s.x1 for s in fig.layout.shapes) == 3


def test_ki_actual_cash_flow_and_scope():
    dates=pd.bdate_range('2020-01-01',periods=6)
    prices=pd.DataFrame({'global':100.,'sweden':100.,'em':100.},index=dates)
    sig=pd.DataFrame({'Signal':[-1,1], 'Signal_Date':dates[[0,3]], 'Available_Date':dates[[1,3]], 'Barometer':[115.,89.]},index=dates[[2,4]])
    p=PortfolioParams({'global':.75,'sweden':.10,'em':.15},scope_keys={'sweden'},rebalance_freq='none',interest_mode='zero')
    r=simulate_portfolio(prices,sig,p)
    a,b=r['events']
    assert a['before'] == 1
    assert a['after'] == pytest.approx(.95)
    assert a['cash_change'] == pytest.approx(5000)
    assert b['cash_change'] == pytest.approx(-5000)
    assert b['after'] == 1
    assert a['signal_date'] < a['date']
    p.derisk_pct=0
    assert simulate_portfolio(prices,sig,p)['events'] == []
