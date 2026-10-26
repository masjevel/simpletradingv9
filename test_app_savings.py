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


def _fake(monkeypatch, rate_ok=True):
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
