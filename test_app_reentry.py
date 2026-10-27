"""UI-tester för kombinerat återköp, KI-lager, nuläge och nya fördjupningar. Syntetiska data."""
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import config
import portfolio


@pytest.fixture
def app_with_cycles(monkeypatch):
    dates = pd.bdate_range("2015-01-01", "2019-12-31")
    x = np.arange(len(dates))
    close = 100 + x * 0.04 + 12 * np.sin(x / 90)
    prices = pd.DataFrame({"Close": close, "Open": close}, index=dates)
    vix = pd.Series(16.0, index=dates, name="VIX")
    vix.loc["2016-09-01":"2016-09-20"] = 45.0
    vix.loc["2018-10-01":"2018-10-10"] = 40.0
    ki_vals = ([100] * 6 + [112, 114, 115, 116] + [105] * 6 + [95, 88, 86, 87, 90, 94] + [100] * 6
               + [111, 113, 115, 114] + [104] * 6 + [92, 88, 89, 91] + [100] * 6)
    ki = pd.DataFrame({"Barometer": [float(v) for v in ki_vals]},
                      index=pd.date_range("2015-01-31", periods=len(ki_vals), freq="ME"))
    fake = types.ModuleType("data")
    fake.fetch_price_series = lambda symbol, *a, **k: prices.copy()
    fake.fetch_vix = lambda: vix
    fake.fetch_fx_rate = lambda: pd.Series(10.0, index=dates)
    fake.fetch_riksbank_rate = lambda *a, **k: pd.Series(0.01, index=pd.date_range('1995-01-02', '2030-12-31', freq='B'))
    fake.fetch_us_cli = lambda *a, **k: None
    fake.fetch_ki_barometer = lambda: ki
    monkeypatch.setitem(sys.modules, "data", fake)
    return AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=90).run()


def test_combined_reentry_steps_reach_portfolio(app_with_cycles, monkeypatch):
    app = app_with_cycles
    assert not app.exception
    captured = []
    original = portfolio.run_ki_vs_bnh

    def capture(prices, orders, params):
        captured.append(orders.copy())
        return original(prices, orders, params)

    monkeypatch.setattr(portfolio, "run_ki_vs_bnh", capture)
    app.radio(key="pf_reentry_mode").set_value("combined").run()
    captured.clear()
    app.checkbox(key="pf_re_trend").set_value(False)
    app.number_input(key="pf_re_vix_calm").set_value(0.0).run()
    assert not app.exception
    orders = captured[0]
    assert "Exposure" in orders.columns
    buys = orders[orders["Signal"] == 1]
    assert (buys["Exposure"] < 1).any()  # minst ett delsteg i trappan
    assert any("vix" in str(t) for t in buys["Trigger"])
    assert any("Läge idag" in i.value for i in app.info)
    assert app.checkbox(key="pf_trend").disabled
    # Utan trappa: första villkoret köper tillbaka allt.
    captured.clear()
    app.checkbox(key="pf_re_staged").set_value(False).run()
    assert not app.exception
    assert set(captured[0].loc[captured[0]["Signal"] == 1, "Exposure"]) == {1.0}
    # Inga villkor och ingen tidsspärr ger en tydlig varning.
    for key in ("pf_re_ki", "pf_re_vix"):
        app.checkbox(key=key).set_value(False)
    app.number_input(key="pf_re_time_stop").set_value(0).run()
    assert not app.exception
    assert any("köper modellen aldrig tillbaka" in w.value for w in app.warning)
    # Återställ portföljen tillbaka till Endast KI.
    app.button(key="reset_pf").click().run()
    assert app.radio(key="pf_reentry_mode").value == "ki_only"


def test_ki_overlays_status_and_deep_dives(app_with_cycles):
    app = app_with_cycles
    labels = [m.label for m in app.metric]
    assert "Månader i följd över säljgränsen" in labels
    assert "KI-modellens läge" in labels
    app.checkbox(key="ki_show_vix").set_value(True)
    app.checkbox(key="ki_show_rsi").set_value(True).run()
    assert not app.exception
    assert len(app.tabs[2].slider) == 3
    app.checkbox(key="pf_robust_run").set_value(True)
    app.checkbox(key="pf_sweden_long").set_value(True).run()
    assert not app.exception
    assert any(m.label == "CAGR KI Sverige (lång)" for m in app.metric)
    app.slider(key="pf_pub_lag").set_value(0).run()
    assert not app.exception
    assert any("publiceringsfördröjning (0 dagar)" in m.value for m in app.markdown)


def test_every_parameter_has_help_and_think_text():
    for key, (title, what, think) in config.PARAM_HELP.items():
        assert title and len(what) > 20 and len(think) > 20, key
        assert "Tänk på" in config.help_text(key)
    src = Path(__file__).with_name("app.py").read_text(encoding="utf-8")
    import re
    missing = [k for k in re.findall(r'H\("([a-z_]+)"\)', src) if k not in config.PARAM_HELP]
    assert not missing
