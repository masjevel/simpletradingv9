"""Historisk ränta (Riksbanken) och portföljens egen trendreferens. Inget nätverk."""
import numpy as np
import pandas as pd
import pytest

import config
import data
import portfolio
import reentry


def test_parse_riksbank_observations_percent_to_decimal():
    payload = [{"date": "2024-01-02", "value": 3.95}, {"date": "2024-01-03", "value": "3,90"},
               {"date": "2024-01-04", "value": None}, {"date": "bad", "value": 1}, "junk"]
    s = data.parse_riksbank_observations(payload)
    assert s.to_dict() == {pd.Timestamp("2024-01-02"): pytest.approx(0.0395), pd.Timestamp("2024-01-03"): pytest.approx(0.039)}
    assert data.parse_riksbank_observations({"observations": payload[:1]}).iloc[0] == pytest.approx(0.0395)
    assert data.parse_riksbank_observations([]).empty


def _clear(func):
    for name in ("clear", "cache_clear"):
        if hasattr(func, name):
            getattr(func, name)()


def test_fetch_riksbank_rate_url_and_failures(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, status, payload):
            self.status_code, self._payload = status, payload

        def json(self):
            return self._payload

    def fake_get(url, **kw):
        calls.append(url)
        return Resp(200, [{"date": "2024-01-02", "value": 4.0}])

    monkeypatch.setattr(data.requests, "get", fake_get)
    _clear(data.fetch_riksbank_rate)
    s = data.fetch_riksbank_rate()
    assert calls[0].startswith(f"https://api.riksbank.se/swea/v1/Observations/{config.RIKSBANK_RATE_SERIES}/1995-01-01/")
    assert s.iloc[0] == pytest.approx(0.04)

    monkeypatch.setattr(data.requests, "get", lambda url, **kw: Resp(429, None))
    _clear(data.fetch_riksbank_rate)
    assert data.fetch_riksbank_rate() is None

    def boom(url, **kw):
        raise ConnectionError("offline")
    monkeypatch.setattr(data.requests, "get", boom)
    _clear(data.fetch_riksbank_rate)
    assert data.fetch_riksbank_rate() is None
    _clear(data.fetch_riksbank_rate)


def test_effective_rate_deduction_floor_and_average():
    raw = pd.Series([0.01, -0.005, 0.03], index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04"]))
    np.testing.assert_allclose(portfolio.effective_rate_series(raw, 0.2, False).to_numpy(), [0.008, -0.007, 0.028])
    np.testing.assert_allclose(portfolio.effective_rate_series(raw, 0.0, True).to_numpy(), [0.01, 0.0, 0.03])
    assert portfolio.effective_rate_series(None) is None
    # 1 jan 1 %, 2-3 jan -0,5 % (framåtfyllt), 4 jan 3 % => snitt över fyra kalenderdagar
    assert portfolio.average_rate(raw, "2020-01-01", "2020-01-04") == pytest.approx((0.01 - 0.005 - 0.005 + 0.03) / 4)


def test_historical_rate_applies_previous_days_rate():
    idx = pd.DatetimeIndex(["2020-01-01", "2021-01-01", "2022-01-01"])  # 366 + 365 dagar
    prices = pd.DataFrame({"a": [100.0] * 3}, index=idx)
    rates = pd.Series([0.05, 0.0], index=pd.DatetimeIndex(["2019-06-01", "2021-01-01"]))
    p = portfolio.PortfolioParams({"a": 1.0}, scope_keys={"a"}, rebalance_freq="none", derisk_pct=100,
                                  interest_mode="historical", interest_rates=rates, initial_capital=1000)
    res = portfolio.simulate_portfolio(prices, pd.DataFrame({"Signal": [-1]}, index=[idx[0]]), p)
    cash = res["components"]["cash"].to_numpy()
    assert cash[1] == pytest.approx(1000 * 1.05 ** (366 / 365))
    assert cash[2] == pytest.approx(cash[1])  # 0 % gällde från 2021-01-01
    assert p.risk_free_annual == pytest.approx(0.025)
    # Bnh-varianten ärver den historiska räntan.
    both = portfolio.run_ki_vs_bnh(prices, None, p)
    assert both["bnh"]["components"]["cash"].iloc[-1] == 0.0


def test_weighted_index_single_and_two_assets():
    idx = pd.bdate_range("2024-01-01", periods=3)
    prices = pd.DataFrame({"a": [100, 110, 121.0], "b": [50, 50, 40.0]}, index=idx)
    np.testing.assert_allclose(portfolio.weighted_index(prices, {"a": 1.0}).to_numpy(), [1, 1.1, 1.21])
    w = portfolio.weighted_index(prices, {"a": .5, "b": .5}).to_numpy()
    np.testing.assert_allclose(w, [1, 1.05, 1.05 * (1 + .5 * .1 + .5 * -.2)])
    assert portfolio.weighted_index(prices, {"a": 0.0}).empty


def test_sweden_only_conditions_identical_with_portfolio_index():
    """Med 100 % Sverige ska den nya referensen ge exakt samma trend-/RSI-villkor som tidigare."""
    dates = pd.bdate_range("2015-01-01", "2019-12-31")
    x = np.arange(len(dates))
    sweden = pd.Series(800 + x * 0.3 + 90 * np.sin(x / 80), index=dates)
    params = reentry.ReentryParams(use_rsi=True, rsi_threshold=40, use_trend=True)
    old = reentry.prepare_conditions(dates, params, reference=sweden)
    new = reentry.prepare_conditions(dates, params, reference=portfolio.weighted_index(sweden.to_frame("sweden"), {"sweden": 1.0}))
    pd.testing.assert_frame_equal(old, new)
    for mode in ("daily_sma200",):
        p2 = reentry.ReentryParams(use_rsi=True, use_trend=True, trend_mode=mode)
        pd.testing.assert_frame_equal(reentry.prepare_conditions(dates, p2, reference=sweden),
                                      reentry.prepare_conditions(dates, p2, reference=portfolio.weighted_index(sweden.to_frame("s"), {"s": 1.0})))


def test_default_publication_lag_is_zero_and_trades_next_month():
    import ki_model
    assert config.KI_PUBLICATION_LAG_DAYS == 0
    assert ki_model.KiParams().publication_lag_days == 0
    ki = pd.Series([115.0, 115.0, 115.0], index=pd.date_range("2024-01-31", periods=3, freq="ME"))
    sig = ki_model.generate_ki_signals(ki, ki_model.KiParams(110, 90, 3, 90, "classic"))
    orders = ki_model.map_signals_to_trading_days(sig, pd.bdate_range("2024-03-01", "2024-04-30"))
    assert list(orders.index) == [pd.Timestamp("2024-04-01")]  # marssiffran -> första handelsdagen i april



OECD_CSV = (
    "DATAFLOW,REF_AREA,FREQ,MEASURE,UNIT_MEASURE,ACTIVITY,ADJUSTMENT,TRANSFORMATION,TIME_HORIZ,METHODOLOGY,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-07,100.86915,A\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-09,100.99928,A\n"
    "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,IX,_Z,AA,IX,_Z,H,2026-08,100.94638,A\n"
)


def test_parse_oecd_sdmx_csv_month_end_sorted_and_series_choice():
    s = data.parse_oecd_sdmx_csv(OECD_CSV)
    assert list(s.index) == [pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-31"), pd.Timestamp("2026-09-30")]
    assert s.iloc[-1] == pytest.approx(100.99928)
    # Om svaret innehåller en annan serie (t.ex. annan enhet) väljs den med flest observationer.
    extra = OECD_CSV + "OECD.SDD.STES:DSD_STES@DF_CLI(4.1),USA,M,LI,PA,_Z,AA,IX,_Z,H,2026-09,0.5,A\n"
    assert data.parse_oecd_sdmx_csv(extra).iloc[-1] == pytest.approx(100.99928)
    with pytest.raises(ValueError):
        data.parse_oecd_sdmx_csv("a,b\n1,2\n")


OECD_JSON_V2 = {"meta": {}, "data": {
    "dataSets": [{"series": {"0:0:0": {"observations": {"0": [100.5], "1": [100.8], "2": [101.0]}},
                             "0:1:0": {"observations": {"0": [0.1]}}}}],
    "structures": [{"dimensions": {"series": [], "observation": [
        {"id": "TIME_PERIOD", "values": [{"id": "2026-07"}, {"id": "2026-08"}, {"id": "2026-09"}]}]}}]}}


def test_parse_oecd_sdmx_json_v1_and_v2():
    s = data.parse_oecd_sdmx_json(OECD_JSON_V2)
    assert list(s.index) == [pd.Timestamp("2026-07-31"), pd.Timestamp("2026-08-31"), pd.Timestamp("2026-09-30")]
    assert s.iloc[-1] == pytest.approx(101.0)
    v1 = {"dataSets": OECD_JSON_V2["data"]["dataSets"], "structure": OECD_JSON_V2["data"]["structures"][0]}
    pd.testing.assert_series_equal(data.parse_oecd_sdmx_json(v1), s)
    with pytest.raises(ValueError):
        data.parse_oecd_sdmx_json({"data": {}})


def test_parse_fred_observations():
    s = data.parse_fred_observations({"observations": [{"date": "2026-08-01", "value": "."}, {"date": "2026-09-01", "value": "100.99"}]})
    assert s.to_dict() == {pd.Timestamp("2026-09-30"): pytest.approx(100.99)}


class _Resp:
    def __init__(self, status, text="", payload=None):
        self.status_code, self.text, self._payload = status, text, payload

    def json(self):
        return self._payload


def test_fetch_us_cli_oecd_first_then_fred_with_key(monkeypatch):
    seen = []

    def oecd_ok(url, **kw):
        seen.append(url)
        return _Resp(200, OECD_CSV)

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(data.requests, "get", oecd_ok)
    _clear(data.fetch_us_cli)
    s = data.fetch_us_cli()
    assert seen[0].startswith("https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/USA.M.LI...AA...H")
    assert "format=csvfile" in seen[0] and s.iloc[-1] == pytest.approx(100.99928)

    # CSV ger fel men JSON fungerar -> JSON används.
    def csv_bad_json_ok(url, **kw):
        if "format=csvfile" in url:
            return _Resp(406)
        return _Resp(200, text=__import__("json").dumps(OECD_JSON_V2))
    monkeypatch.setattr(data.requests, "get", csv_bad_json_ok)
    _clear(data.fetch_us_cli)
    assert data.fetch_us_cli().iloc[-1] == pytest.approx(101.0)

    # OECD nere, FRED-nyckel finns -> FRED-API används.
    calls = []

    def oecd_down_fred_ok(url, params=None, **kw):
        calls.append((url, params))
        if "sdmx.oecd.org" in url:
            return _Resp(503)
        return _Resp(200, payload={"observations": [{"date": "2026-09-01", "value": "101.0"}]})

    monkeypatch.setenv("FRED_API_KEY", "testnyckel")
    monkeypatch.setattr(data.requests, "get", oecd_down_fred_ok)
    _clear(data.fetch_us_cli)
    s = data.fetch_us_cli()
    assert s.iloc[-1] == pytest.approx(101.0)
    assert calls[-1][0] == config.FRED_API_URL and calls[-1][1]["api_key"] == "testnyckel"
    assert calls[-1][1]["series_id"] == config.US_CLI_SERIES

    # Allt nere -> None med begriplig orsak.
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(data.requests, "get", lambda url, **kw: _Resp(403))
    _clear(data.fetch_us_cli)
    assert data.fetch_us_cli() is None
    assert "OECD svarade 403" in data.last_error("us_cli") and "FRED-nyckel" in data.last_error("us_cli")
    _clear(data.fetch_us_cli)


def test_failures_are_not_cached_but_successes_are(monkeypatch):
    calls = []

    def flaky(url, **kw):
        calls.append(url)
        return _Resp(503) if len(calls) <= 2 else _Resp(200, OECD_CSV)  # två försök per anrop (CSV + JSON)

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setattr(data.requests, "get", flaky)
    _clear(data.fetch_us_cli)
    assert data.fetch_us_cli() is None          # misslyckas ...
    assert data.fetch_us_cli() is not None      # ... men nästa anrop försöker igen och lyckas
    n = len(calls)
    assert data.fetch_us_cli() is not None      # lyckat svar ligger i cachen
    assert len(calls) == n
    _clear(data.fetch_us_cli)


def test_rescale_cli_scale_and_no_lookahead():
    import signal_sources
    months = pd.date_range("1960-01-31", periods=400, freq="ME")
    rng = np.random.default_rng(1)
    cli = pd.Series(100 + rng.normal(0, 1.2, len(months)), index=months)
    scaled = signal_sources.rescale_to_barometer(cli, min_months=120)
    assert scaled.iloc[:119].isna().all() and scaled.iloc[119:].notna().all()
    # Långt fram är skalan ungefär KI:s: standardavvikelse ~10 kring 100.
    assert (scaled.iloc[200:] - 100).pow(2).mean() ** 0.5 == pytest.approx(10, rel=0.15)
    # Ingen look-ahead: ändrade framtida värden påverkar inte tidigare skalade värden.
    changed = cli.copy(); changed.iloc[300:] += 5
    pd.testing.assert_series_equal(scaled.iloc[:300], signal_sources.rescale_to_barometer(changed, 120).iloc[:300])
    frame = signal_sources.as_signal_frame(scaled)
    assert list(frame.columns) == ["Barometer"] and frame["Barometer"].notna().all()
