"""UI-tester för Månadssparande, historisk ränta och portföljens trendreferens. Syntetiska data."""
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
import reentry


def _fake(monkeypatch, rate_ok=True, cli=None):
    dates = pd.bdate_range("2010-01-01", "2019-12-31")
    x = np.arange(len(dates))
    sweden = pd.DataFrame({"Close": 100 + x * 0.02 + 15 * np.sin(x / 120)}, index=dates)
    world = pd.DataFrame({"Close": 50 + x * 0.03 - 8 * np.sin(x / 60)}, index=dates)
    sweden["Open"] = sweden["Close"]
    world["Open"] = world["Close"]
    vix = pd.Series(18.0, index=dates, name="VIX")
    vix.loc["2015-08-20":"2015-09-05"] = 40.0
    ki_vals = ([100] * 30 + [112, 114, 115, 116] + [105] * 6 + [95, 88, 86, 87, 90, 94] + [100] * 60)
    ki = pd.DataFrame({"Barometer": [float(v) for v in ki_vals]},
                      index=pd.date_range("2010-01-31", periods=len(ki_vals), freq="ME"))
    fake = types.ModuleType("data")
    fake.fetch_price_series = lambda symbol, *a, **k: (world if symbol == config.PORTFOLIO_PROXIES["global"]["ticker"] else sweden).copy()
    fake.fetch_vix = lambda: vix
    fake.fetch_fx_rate = lambda: pd.Series(10.0, index=dates)
    fake.fetch_ki_barometer = lambda: ki
    fake.fetch_riksbank_rate = (lambda *a, **k: pd.Series(0.02, index=dates)) if rate_ok else (lambda *a, **k: None)
    fake.fetch_us_cli = lambda *a, **k: cli
    monkeypatch.setitem(sys.modules, "data", fake)
    return AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=120)


def test_savings_tab_metrics_extra_deposit_and_start_years(monkeypatch):
    app = _fake(monkeypatch).run()
    assert not app.exception
    assert len(app.tabs) == 5
    labels = [m.label for m in app.tabs[4].metric]
    assert "Insatt totalt" in labels and "Slutvärde KI-strategi" in labels
    # Startdatum 2007 före data => info om att sparandet startar när kursdata finns.
    assert any("sparandet startar då" in i.value for i in app.tabs[4].info)
    invested = next(m.value for m in app.tabs[4].metric if m.label == "Insatt totalt")
    to_num = lambda v: float(v.replace(" kr", "").replace("\xa0", "").replace(" ", ""))
    # Fler än tre extra insättningar: fem rader, varav en före kursdata (2008) och en ofullständig.
    app.session_state["sv_extra_data"] = pd.DataFrame({
        "Datum": pd.to_datetime(["2008-10-15", "2012-03-01", "2013-05-02", "2015-06-01", "2017-09-01", "2018-02-01", None]),
        "Belopp (kr)": [99_000.0, 10_000.0, 20_000.0, 30_000.0, 40_000.0, 50_000.0, 1_000.0],
        "Beskrivning": ["Arv", "Bonus", "Sålt bil", "Bonus", "Arv", "Försäljning", "saknar datum"],
    })
    app.run()
    assert not app.exception
    invested_extra = next(m.value for m in app.tabs[4].metric if m.label == "Insatt totalt")
    assert to_num(invested_extra) - to_num(invested) == pytest.approx(150_000)
    assert any("utanför sparperioden" in w.value and "Arv" in w.value for w in app.tabs[4].warning)
    assert any("1 rad(er) saknar datum" in w.value for w in app.tabs[4].warning)
    assert any("6 extra insättningar" in c.value for c in app.tabs[4].caption)
    app.checkbox(key="sv_compare_run").set_value(True).run()
    assert not app.exception
    assert any(df.value.shape[0] >= 5 and "Startår" in df.value.columns for df in app.tabs[4].dataframe)
    app.button(key="reset_sv").click().run()
    assert not app.exception
    assert next(m.value for m in app.tabs[4].metric if m.label == "Insatt totalt") == invested


def test_historical_rate_default_and_fallback(monkeypatch):
    app = _fake(monkeypatch).run()
    assert not app.exception
    assert app.selectbox(key="pf_interest_mode").value == "historical"
    assert any("Snitt under perioden" in c.value and "2.00%" in c.value for c in app.tabs[3].caption)
    app2 = _fake(monkeypatch, rate_ok=False).run()
    assert not app2.exception
    assert any("Historisk ränta kunde inte hämtas" in w.value for w in app2.tabs[3].warning)


def test_trend_reference_follows_portfolio_weights(monkeypatch):
    seen = []
    original = reentry.prepare_conditions

    def capture(calendar, params, reference=None, **kw):
        seen.append(None if reference is None else reference.copy())
        return original(calendar, params, reference=reference, **kw)

    monkeypatch.setattr(reentry, "prepare_conditions", capture)
    app = _fake(monkeypatch).run()
    app.slider(key="pf_w_global").set_value(100)
    app.slider(key="pf_w_sweden").set_value(0)
    app.slider(key="pf_w_em").set_value(0)
    seen.clear()
    app.radio(key="pf_reentry_mode").set_value("combined").run()
    assert not app.exception
    ref = seen[0]
    world = 50 + np.arange(len(ref)) * 0.03 - 8 * np.sin(np.arange(len(ref)) / 60)
    # Referensen ska vara Global-serien (normaliserad), inte Sverige.
    np.testing.assert_allclose(ref.to_numpy(), world / world[0], rtol=1e-9)


def _metric(app, label):
    return next(m.value for m in app.tabs[4].metric if m.label == label)


def test_amount_fields_show_spaces_and_form_submit(monkeypatch):
    app = _fake(monkeypatch).run()
    assert not app.exception
    assert app.text_input(key="sv_monthly").value == "2 000"
    assert app.text_input(key="pf_portfolio_initial_capital").value == "100 000"
    before = _metric(app, "Insatt totalt")
    # I formuläret räknas inget om förrän knappen trycks.
    app.text_input(key="sv_initial").set_value("10000")
    app.run()
    assert _metric(app, "Insatt totalt") == before
    app.text_input(key="sv_initial").set_value("10000")
    next(b for b in app.button if b.label == "Beräkna sparplanen").click().run()
    assert not app.exception
    assert app.text_input(key="sv_initial").value == "10 000"
    to_num = lambda v: float(v.replace(" kr", "").replace("\xa0", "").replace(" ", ""))
    assert to_num(_metric(app, "Insatt totalt")) - to_num(before) == pytest.approx(10_000)
    # Ogiltigt belopp ger varning och standardvärdet används.
    app.text_input(key="sv_monthly").set_value("tvåtusen")
    next(b for b in app.button if b.label == "Beräkna sparplanen").click().run()
    assert any("är inte ett belopp" in w.value for w in app.tabs[4].warning)
    # Startkapital utanför formulär formateras direkt.
    app.text_input(key="pf_portfolio_initial_capital").set_value("250000").run()
    assert app.text_input(key="pf_portfolio_initial_capital").value == "250 000"
    assert any("Startkapital: 250 000 kr" in m.value for m in app.tabs[3].markdown)


def test_us_cli_signal_source_and_long_history(monkeypatch):
    months = pd.date_range("1990-01-31", "2019-12-31", freq="ME")
    t = np.arange(len(months))
    cli = pd.Series(100 + 1.5 * np.sin(t / 14), index=months)
    app = _fake(monkeypatch, cli=cli).run()
    assert not app.exception
    app.selectbox(key="pf_signal_source").set_value("us_cli").run()
    assert not app.exception
    assert app.slider(key="pf_pub_lag_us").value == config.DEFAULT_US_CLI_LAG_DAYS
    assert any("Signalkälla: USA" in m.value for m in app.tabs[3].markdown)
    assert any("OECD-data är öppna" in c.value for c in app.tabs[3].caption)
    labels = [m.label for m in app.tabs[3].metric]
    assert "CAGR (KI-strategi)" in labels
    app.checkbox(key="pf_us_long").set_value(True).run()
    assert not app.exception
    assert any(m.label == "CAGR KI USA (lång)" for m in app.tabs[3].metric)
    # Sparfliken använder samma signalkälla.
    assert "Slutvärde KI-strategi" in [m.label for m in app.tabs[4].metric]


def test_us_cli_missing_gives_clear_error(monkeypatch):
    app = _fake(monkeypatch, cli=None).run()
    app.selectbox(key="pf_signal_source").set_value("us_cli").run()
    assert not app.exception
    assert any("OECD:s ledande indikator för USA kunde inte hämtas" in e.value for e in app.tabs[3].error)
    assert any("Portföljdata saknas" in i.value for i in app.tabs[4].info)


def test_sweep_runs_only_when_requested(monkeypatch):
    import portfolio
    calls = []
    original = portfolio.simulate_portfolio
    monkeypatch.setattr(portfolio, "simulate_portfolio", lambda *a, **k: (calls.append(1), original(*a, **k))[1])
    app = _fake(monkeypatch).run()
    base = len(calls)
    calls.clear()
    app.checkbox(key="pf_sweep_run").set_value(True).run()
    assert not app.exception
    assert len(calls) - base >= 20  # 5 regler × 4 avriskningsgrader
    assert any("Återköpsregel" in df.value.columns for df in app.tabs[3].dataframe)
