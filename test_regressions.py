import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import metrics
import portfolio
from indicators import compute_rsi
from ki_model import map_signals_to_trading_days


@pytest.mark.parametrize('available,expected', [
    ('2024-01-05', '2024-01-08'),
    ('2024-01-05 12:00', '2024-01-08'),
    ('2024-01-06', '2024-01-08'),
    ('2024-01-08', '2024-01-10'),  # missing Tuesday is a market holiday
    ('2024-01-10', None),
])
def test_execution_strictly_after_availability(available, expected):
    days = pd.to_datetime(['2024-01-05', '2024-01-08', '2024-01-10'])
    signals = pd.DataFrame({'Signal': [-1], 'Signal_Type': ['KI SÄLJ'],
                            'Available_Date': [pd.Timestamp(available)]})
    mapped = map_signals_to_trading_days(signals, days)
    if expected is None:
        assert mapped.empty
    else:
        assert mapped.index[0] == pd.Timestamp(expected)
        assert mapped.index[0] > signals.Available_Date.iloc[0]
        assert mapped.index[0].normalize() > signals.Available_Date.iloc[0].normalize()


def test_wilder_rsi_exact_reference():
    # Hand calculation, N=3: initial gains=(3+0+3)/3=2,
    # losses=(0+3+0)/3=1. Recursion gives 4/3,5/3 then 17/9,10/9.
    close = pd.Series([10., 13., 10., 13., 10., 13.], name='Close')
    actual = compute_rsi(close, 3)
    assert actual.iloc[:3].isna().all()
    np.testing.assert_allclose(actual.iloc[3:], [200/3, 400/9, 1700/27], rtol=0, atol=1e-12)
    assert actual.name == 'RSI'
    pd.testing.assert_series_equal(compute_rsi(close.iloc[:5], 3), actual.iloc[:5])


def test_wilder_fourteen_period_published_example_values():
    # Conventional Wilder worksheet price example; full precision (no intermediate rounding).
    close = pd.Series([44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,
                       45.84,46.08,45.89,46.03,45.61,46.28,46.28,46.00,
                       46.03,46.41,46.22,45.64,46.21])
    expected = [70.46413502109705,66.24961855355505,66.48094183471265,
                69.34685316290866,66.29471265892624,57.91502067008556,
                62.8807183099624]
    result = compute_rsi(close)
    assert result.iloc[:14].isna().all()
    np.testing.assert_allclose(result.iloc[14:], expected, rtol=0, atol=1e-10)


@pytest.mark.parametrize('values,expected', [([1,2,3,4],100),([4,3,2,1],0),([2,2,2,2],50)])
def test_wilder_edge_cases(values, expected):
    assert compute_rsi(pd.Series(values),3).iloc[-1] == expected


def test_rsi_gap_requires_fresh_seed():
    result = compute_rsi(pd.Series([1.,2.,3.,np.nan,4.,5.,6.]),2)
    assert result.iloc[3:6].isna().all()
    assert result.iloc[6] == 100


@pytest.mark.parametrize('period', [0,-1,1.5])
def test_invalid_rsi_period(period):
    with pytest.raises(ValueError):
        compute_rsi(pd.Series([1.,2.]),period)


def test_fx_never_uses_future_and_keeps_off_calendar_history():
    dates = pd.to_datetime(['2024-01-01','2024-01-03','2024-01-05'])
    prices = pd.Series([10.,10.,10.],index=dates)
    fx = pd.Series([9.,11.],index=pd.to_datetime(['2024-01-02','2024-01-05']))
    actual = portfolio.to_common_currency(prices,fx)
    assert np.isnan(actual.iloc[0])
    assert actual.iloc[1:].tolist() == [90.,110.]
    altered = fx.copy(); altered.iloc[-1] = 999
    pd.testing.assert_series_equal(actual.iloc[:2],portfolio.to_common_currency(prices,altered).iloc[:2])
    aligned = portfolio.align_prices({'a':actual,'b':prices})
    assert aligned.index[0] == dates[1]
    assert portfolio.align_prices({'a': portfolio.to_common_currency(prices,fx.iloc[:0])}).empty


@pytest.mark.parametrize('mode,expected_rate',[('fixed',.025),('zero',0.)])
def test_selected_interest_rate_in_risk_report(mode, expected_rate):
    params = portfolio.PortfolioParams({'a':1.},interest_mode=mode,annual_interest_rate=.025)
    assert params.risk_free_annual == expected_rate
    equity = pd.Series([100.,101.,99.,102.,98.,103.],index=pd.bdate_range('2024-01-01',periods=6))
    report = metrics.build_risk_report(equity,pd.Series(1,index=equity.index),[],params.risk_free_annual)
    returns = np.array([.01,99/101-1,102/99-1,98/102-1,103/98-1])
    excess = returns-expected_rate/252
    assert report.sharpe == pytest.approx(excess.mean()/excess.std(ddof=1)*np.sqrt(252))
    assert report.sortino == pytest.approx(excess.mean()/excess[excess<0].std(ddof=1)*np.sqrt(252))


def test_costs_on_initial_derisk_and_buyback():
    dates = pd.bdate_range('2024-01-01',periods=4)
    prices = pd.DataFrame({'a':[100.]*4},index=dates)
    signals = pd.DataFrame({'Signal':[-1,1]},index=dates[1:3])
    p = portfolio.PortfolioParams({'a':1.},scope_keys={'a'},derisk_pct=100,
        initial_capital=1000,rebalance_freq='none',interest_mode='zero',cost_bps=60,slippage_bps=40)
    result = portfolio.run_ki_vs_bnh(prices,signals,p)
    ki=result['ki']; rate=.01
    invested=1000/(1+rate); sold=invested*(1-rate); bought=sold/(1+rate)
    np.testing.assert_allclose(ki['equity'],[invested,sold,bought,bought])
    np.testing.assert_allclose(ki['transaction_costs'],[1000-invested,invested*rate,sold-bought,0])
    np.testing.assert_allclose(result['bnh']['equity'],[invested]*4)
    assert metrics.total_return(ki['equity']) == pytest.approx((bought/1000-1)*100)
    assert metrics.max_drawdown(ki['equity']) == pytest.approx((bought/1000-1)*100)
    assert (ki['components']['cash'] >= 0).all()


@pytest.mark.parametrize('frequency', ['monthly','quarterly','annual'])
def test_rebalance_costs_and_benchmark_fairness(frequency):
    dates = pd.to_datetime(['2023-12-29','2024-01-02','2024-01-03'])
    prices=pd.DataFrame({'a':[100.,200.,200.],'b':[100.,100.,100.]},index=dates)
    p=portfolio.PortfolioParams({'a':.5,'b':.5},initial_capital=1000,rebalance_freq=frequency,
                               interest_mode='zero',cost_bps=100)
    out=portfolio.run_ki_vs_bnh(prices,None,p)
    ki=out['ki']; opening=1000/1.01
    # Before rebalance: a=opening, b=opening/2. Total turnover=opening/2.
    assert ki['transaction_costs'].iloc[1] == pytest.approx(opening/2*.01)
    assert ki['equity'].iloc[1] == pytest.approx(opening*1.5-opening/2*.01)
    np.testing.assert_allclose(ki['weights'][['a','b']].iloc[1], [.5,.5])
    assert ki['transaction_costs'].iloc[2] == 0
    for key in ['equity','transaction_costs','turnover']:
        pd.testing.assert_series_equal(ki[key],out['bnh'][key])


def test_simultaneous_signal_and_rebalance_charged_once():
    dates=pd.to_datetime(['2023-12-29','2024-01-02'])
    prices=pd.DataFrame({'a':[100.,100.]},index=dates)
    signals=pd.DataFrame({'Signal':[-1]},index=dates[1:])
    p=portfolio.PortfolioParams({'a':1.},scope_keys={'a'},derisk_pct=50,initial_capital=1000,
                               interest_mode='zero',cost_bps=100)
    result=portfolio.simulate_portfolio(prices,signals,p)
    opening=1000/1.01
    net=opening*(1-.01)/(1-.005)
    assert result['equity'].iloc[1] == pytest.approx(net)
    assert result['transaction_costs'].iloc[1] == pytest.approx(opening-net)
    assert result['weights']['cash'].iloc[1] == pytest.approx(.5)


@pytest.mark.parametrize('cost,slip', [(-1,0),(0,-1),(10000,0),(float('nan'),0)])
def test_invalid_costs_rejected(cost,slip):
    with pytest.raises(ValueError):
        portfolio.simulate_portfolio(pd.DataFrame({'a':[1.]},index=pd.to_datetime(['2024-01-01'])),None,
            portfolio.PortfolioParams({'a':1},cost_bps=cost,slippage_bps=slip))


def test_app_all_report_and_portfolio_call_sites_are_wired():
    # Check actual UI call sites without importing Streamlit or fetching market data.
    tree=ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8'))
    reports=[]; portfolios=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute):
            continue
        if node.func.attr in {'build_risk_report','sharpe_ratio','sortino_ratio'}:
            reports.append(node)
            kw={k.arg:k.value for k in node.keywords}
            expected_rate = 'tech_risk_free' if 'bt[' in ast.unparse(node.args[0]) else 'risk_free_annual'
            assert ast.unparse(kw['risk_free_annual']) == expected_rate
        if node.func.attr == 'PortfolioParams':
            portfolios.append(node)
            kw={k.arg:k.value for k in node.keywords}
            assert ast.unparse(kw['cost_bps']) == 'pf_cost_bps'
            assert ast.unparse(kw['slippage_bps']) == 'pf_slippage_bps'
            assert ast.unparse(kw['interest_rates']) == 'interest_rates'
            assert ast.unparse(kw['interest_mode']) == 'effective_interest_mode'
    # En enda konstruktion; alla jämförelser (svep, Sverige, sparande) ärver via dataclasses.replace(pf_params, ...).
    assert len(reports)==6 and len(portfolios)==1
    src = Path(__file__).with_name('app.py').read_text(encoding='utf-8')
    assert "dataclasses.replace(pf_params, derisk_pct=float(lvl))" in src
    assert "dataclasses.replace(pf_params, base_weights={'sweden': 1.0}, scope_keys={'sweden'})" in src
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='risk_free_annual' for t in n.targets))
    for mode,expected in [('fixed',.025),('zero',0.)]:
        assert eval(compile(ast.Expression(assignment.value),'<UI rate>','eval'),
                    {'annual_interest_rate':.025,'interest_mode':mode}) == expected


def test_initial_cost_in_cagr_calmar_and_drawdown_chart():
    equity=pd.Series([990.,1100.],index=pd.to_datetime(['2020-01-01','2021-01-01']))
    equity.attrs['initial_capital']=1000.
    expected_cagr=((1100/1000)**(365.25/366)-1)*100
    assert metrics.cagr(equity)==pytest.approx(expected_cagr)
    assert metrics.calmar_ratio(equity)==pytest.approx(expected_cagr)
    np.testing.assert_allclose(metrics.compute_drawdown(equity.to_numpy(),1000),[-1.,0.])
